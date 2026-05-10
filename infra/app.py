#!/usr/bin/env python3
import aws_cdk as cdk
from stack import PricingStack

app = cdk.App()

PricingStack(
    app,
    "DamePricingStack",
    env=cdk.Environment(
        account=app.node.try_get_context("account") or None,
        region=app.node.try_get_context("region") or None,
    ),
)

app.synth()
