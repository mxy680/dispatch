def init():
    pass


def pre_mutation(context):
    # Only mutate the two target modules
    if context.filename not in (
        "agents/command_builder.py",
        "services/security_analyzer.py",
    ):
        context.skip = True
