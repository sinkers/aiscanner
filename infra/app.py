#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stack import CertificateStack, PricingStack

app = cdk.App()

account = app.node.try_get_context("account") or os.environ.get("CDK_DEFAULT_ACCOUNT")
region  = app.node.try_get_context("region")  or os.environ.get("CDK_DEFAULT_REGION", "ap-southeast-2")

# ACM certificate — must be in us-east-1 for CloudFront
cert_stack = CertificateStack(
    app, "DamePricingCertStack",
    env=cdk.Environment(account=account, region="us-east-1"),
    cross_region_references=True,
)

# Main stack — S3, CloudFront, Lambda, EventBridge, Route53
pricing_stack = PricingStack(
    app, "DamePricingStack",
    certificate=cert_stack.certificate,
    env=cdk.Environment(account=account, region=region),
    cross_region_references=True,
)
pricing_stack.add_dependency(cert_stack)

app.synth()
