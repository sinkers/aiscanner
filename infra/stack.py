import os
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_certificatemanager as acm,
    aws_route53 as route53,
    aws_route53_targets as route53_targets,
)
from constructs import Construct

DOMAIN      = "aiinfo.dametech.net"
HOSTED_ZONE = "Z07889022X9MFJH9G0F7M"
ZONE_NAME   = "dametech.net"


class CertificateStack(Stack):
    """
    ACM certificate for the custom domain.
    Must be deployed to us-east-1 — CloudFront only accepts certs from that region.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self, "HostedZone",
            hosted_zone_id=HOSTED_ZONE,
            zone_name=ZONE_NAME,
        )

        self.certificate = acm.Certificate(
            self, "Certificate",
            domain_name=DOMAIN,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        CfnOutput(self, "CertificateArn", value=self.certificate.certificate_arn)


class PricingStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        certificate: acm.ICertificate,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------
        # S3 bucket — private, served exclusively through CloudFront
        # ------------------------------------------------------------------
        # IMPORTANT: versioning is enabled to protect historical pricing data.
        # Historical snapshots (snapshots/YYYY-MM-DD.json) and per-provider/model
        # rollup histories are the source of truth for all trend data — they must
        # NEVER be overwritten or deleted. Versioning provides a safety net against
        # accidental overwrites from Lambda bugs or bad deploys.
        bucket = s3.Bucket(
            self,
            "PricingBucket",
            bucket_name=f"dame-openrouter-pricing-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            versioned=True,
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.HEAD],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=3600,
                )
            ],
        )

        # ------------------------------------------------------------------
        # CloudFront distribution with Origin Access Control
        # ------------------------------------------------------------------
        oac = cloudfront.S3OriginAccessControl(self, "OAC")

        distribution = cloudfront.Distribution(
            self,
            "Distribution",
            domain_names=[DOMAIN],
            certificate=certificate,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    bucket,
                    origin_access_control=oac,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                compress=True,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
            ],
            comment="DAME OpenRouter Pricing site",
        )

        # ------------------------------------------------------------------
        # Route53 alias — aiinfo.dametech.net → CloudFront distribution
        # ------------------------------------------------------------------
        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self, "HostedZone",
            hosted_zone_id=HOSTED_ZONE,
            zone_name=ZONE_NAME,
        )

        route53.ARecord(
            self, "AliasRecord",
            zone=hosted_zone,
            record_name="aiinfo",
            target=route53.RecordTarget.from_alias(
                route53_targets.CloudFrontTarget(distribution)
            ),
        )

        # ------------------------------------------------------------------
        # Lambda — collector + rollup generator
        # ------------------------------------------------------------------
        collector = lambda_.Function(
            self,
            "Collector",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "..", "lambda")
            ),
            timeout=Duration.minutes(15),
            memory_size=512,
            description="Daily OpenRouter pricing snapshot and rollup generator",
            environment={
                "S3_BUCKET": bucket.bucket_name,
                "OPENROUTER_API_TOKEN": "REDACTED_OPENROUTER_TOKEN_2",
                # GPU API keys are read from SSM Parameter Store at runtime.
                # Set them once with:  make configure-gpu  (or load from .env)
                # Env vars here are a fallback for local testing only.
                "RUNPOD_API_KEY":     os.environ.get("RUNPOD_API_KEY", ""),
                "VAST_API_KEY":       os.environ.get("VAST_API_KEY", ""),
                "LAMBDA_LABS_API_KEY": os.environ.get("LAMBDA_LABS_API_KEY", ""),
            },
        )

        bucket.grant_read_write(collector)

        # Allow Lambda to read GPU API keys from SSM Parameter Store.
        # Keys live at /dame/gpu/runpod_api_key and /dame/gpu/vast_api_key.
        collector.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/dame/gpu/*"
                ],
            )
        )

        # ------------------------------------------------------------------
        # EventBridge rule — daily at 00:00 UTC
        # ------------------------------------------------------------------
        rule = events.Rule(
            self,
            "DailySchedule",
            schedule=events.Schedule.cron(hour="0", minute="0"),
            description="Daily OpenRouter pricing collection",
        )
        rule.add_target(targets.LambdaFunction(collector))

        # ------------------------------------------------------------------
        # Outputs
        # ------------------------------------------------------------------
        CfnOutput(self, "BucketName", value=bucket.bucket_name)
        CfnOutput(self, "SiteURL", value=f"https://{DOMAIN}")
        CfnOutput(self, "CloudFrontURL", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "LambdaName", value=collector.function_name)
