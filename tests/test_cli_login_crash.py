"""세션58 ATOM-3 (upstream 519483b #211): regression guard for `nlm login`
crash on expired auth.

Bug (upstream): when running `nlm login --check` against an expired profile,
the inner NotebookLMClient.list_notebooks() raises ClientAuthenticationError
(NOT NLMError), which propagates as a raw exception traceback — crashing the
CLI instead of failing gracefully with a typer.Exit(2).

Fix: extend the except clause in cli.main.login_callback() to catch BOTH
NLMError AND ClientAuthenticationError.

This guard inspects the live source of login_callback() so we catch any
future regression that removes the import or narrows the except tuple.
"""

import inspect

from notebooklm_tools.cli.main import login_callback


def test_login_callback_handles_client_authentication_error():
    """login_callback() must import ClientAuthenticationError and include it
    in its except tuple — otherwise expired-auth path crashes the CLI."""
    src = inspect.getsource(login_callback)

    # Import must be present so the name resolves inside the function body.
    assert "from notebooklm_tools.core.errors import ClientAuthenticationError" in src, (
        "login_callback should import ClientAuthenticationError "
        "(세션58 ATOM-3 / upstream #211)"
    )

    # except tuple must include ClientAuthenticationError alongside NLMError.
    assert "(NLMError, ClientAuthenticationError)" in src, (
        "login_callback's except clause should catch (NLMError, "
        "ClientAuthenticationError) — narrowing back to NLMError alone "
        "regresses upstream #211"
    )


def test_client_authentication_error_is_catchable_in_combined_tuple():
    """The except (NLMError, ClientAuthenticationError) tuple must actually
    catch a raised ClientAuthenticationError at runtime (sanity check on the
    inheritance/import wiring)."""
    from notebooklm_tools.core.errors import ClientAuthenticationError
    from notebooklm_tools.core.exceptions import NLMError

    caught = False
    try:
        raise ClientAuthenticationError("Authentication expired")
    except (NLMError, ClientAuthenticationError):
        caught = True
    assert caught, "Combined except tuple must catch ClientAuthenticationError"
