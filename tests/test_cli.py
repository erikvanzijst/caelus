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

    # Delete the user (retrieve ID from list output)
    # Extract user ID from list output (format: "{id} {email} {created_at}")
    lines = [line for line in result.output.splitlines() if line.strip()]
    # Assume first line contains the created user
    first_line = lines[0]
    user_id = int(first_line.split()[0])
    del_result = runner.invoke(app, ["delete-user", str(user_id)])
    assert del_result.exit_code == 0
    assert f"Deleted user {user_id}" in del_result.output

    # Verify user no longer listed
    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    assert "cli@example.com" not in result.output
    runner, app = cli_runner

    result = runner.invoke(app, ["create-user", "cli@example.com"])
    assert result.exit_code == 0
    assert "Created user" in result.output

    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    assert "cli@example.com" in result.output
