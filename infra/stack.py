import os
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct


class PricingStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------
        # S3 bucket — private, served exclusively through CloudFront
        # ------------------------------------------------------------------
        bucket = s3.Bucket(
            self,
            "PricingBucket",
            bucket_name=f"dame-openrouter-pricing-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,  # don't delete data on stack destroy
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
            # Return index.html for 403s so direct deep-links work
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
                # Token is already in the codebase; move to Secrets Manager if needed
                "OPENROUTER_API_TOKEN": "REDACTED_OPENROUTER_TOKEN_1",
            },
        )

        bucket.grant_read_write(collector)

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
        CfnOutput(
            self,
            "CloudFrontURL",
            value=f"https://{distribution.distribution_domain_name}",
        )
        CfnOutput(self, "LambdaName", value=collector.function_name)
