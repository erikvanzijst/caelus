from __future__ import annotations


def test_cli_user_flow(cli_runner):
    runner, app = cli_runner

    # Create user
    result = runner.invoke(app, ["create-user", "cli@example.com"])
    assert result.exit_code == 0
    assert "Created user" in result.output

    # List users to verify creation
    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    assert "cli@example.com" in result.output

    # TODO: grab the newly created user from the database or the user_service and retrieve its id for use in the next section
    user_id = 1

    del_result = runner.invoke(app, ["delete-user", str(user_id)])
    assert del_result.exit_code == 0
    assert f"Deleted user" in del_result.output
    # TODO: verify user is actually deleted from the database

    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    assert result.output.strip() == ""

    result = runner.invoke(app, ["create-user", "cli@example.com"])
    assert result.exit_code == 0
    assert "Created user" in result.output

    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    assert "cli@example.com" in result.output
