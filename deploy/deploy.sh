#!/usr/bin/env bash
set -euo pipefail

echo "=== DAME OpenRouter Pricing — Deploy ==="
echo ""

# ------------------------------------------------------------------
# Check prerequisites
# ------------------------------------------------------------------
if ! aws sts get-caller-identity &>/dev/null; then
    echo "ERROR: No AWS credentials. Run 'aws configure' first."
    exit 1
fi

AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region 2>/dev/null || echo "ap-southeast-2")
echo "Account : $AWS_ACCOUNT"
echo "Region  : $AWS_REGION"
echo ""

if ! command -v cdk &>/dev/null; then
    echo "Installing AWS CDK CLI..."
    npm install -g aws-cdk
fi

# ------------------------------------------------------------------
# Install Python CDK dependencies
# ------------------------------------------------------------------
echo "Installing CDK Python dependencies..."
pip install -r infra/requirements.txt -q

# ------------------------------------------------------------------
# Bootstrap CDK environment (safe to re-run)
# ------------------------------------------------------------------
echo "Bootstrapping CDK environments..."
# us-east-1 is required for the ACM certificate stack (CloudFront constraint)
(cd infra && cdk bootstrap "aws://$AWS_ACCOUNT/us-east-1" --quiet)
(cd infra && cdk bootstrap "aws://$AWS_ACCOUNT/$AWS_REGION" --quiet)

# ------------------------------------------------------------------
# Deploy stack
# ------------------------------------------------------------------
echo "Deploying DamePricingStack..."
(cd infra && cdk deploy --require-approval never --outputs-file ../cdk-outputs.json)

# ------------------------------------------------------------------
# Extract stack outputs
# ------------------------------------------------------------------
BUCKET_NAME=$(python3 -c "
import json
with open('cdk-outputs.json') as f:
    d = json.load(f)
stack = list(d.values())[0]
print(stack['BucketName'])
")

CF_URL=$(python3 -c "
import json
with open('cdk-outputs.json') as f:
    d = json.load(f)
stack = list(d.values())[0]
print(stack['CloudFrontURL'])
")

LAMBDA_NAME=$(python3 -c "
import json
with open('cdk-outputs.json') as f:
    d = json.load(f)
stack = list(d.values())[0]
print(stack['LambdaName'])
")

echo ""
echo "Stack outputs:"
echo "  Bucket   : s3://$BUCKET_NAME"
echo "  Site     : $CF_URL"
echo "  Lambda   : $LAMBDA_NAME"

# ------------------------------------------------------------------
# Seed S3 with existing data and upload UI
# ------------------------------------------------------------------
echo ""
echo "Seeding S3 with existing data..."
python3 scripts/bootstrap_s3.py "$BUCKET_NAME" --upload-ui

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo "=== Deploy complete ==="
echo ""
echo "  Site URL : $CF_URL"
echo ""
echo "The Lambda runs daily at 00:00 UTC. To trigger it manually:"
echo "  aws lambda invoke --function-name $LAMBDA_NAME --log-type Tail /tmp/out.json"
echo "  base64 -d <<< \$(python3 -c \"import json; print(json.load(open('/tmp/out.json')).get('LogResult',''))\")"
