#!/usr/bin/env python3
import aws_cdk as cdk

from stacks.backend_stack import BackendStack

app = cdk.App()
BackendStack(app, "LlmsTxtBackend")
app.synth()
