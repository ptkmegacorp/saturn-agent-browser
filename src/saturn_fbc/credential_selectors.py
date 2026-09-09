"""Shared DOM selectors for credential fields."""

PASSWORD_SELECTORS = [
    "input[type=password]",
    "input[autocomplete=current-password]",
    "input[autocomplete=new-password]",
]

USER_SELECTORS = [
    "input[type=email]",
    "input[name*=user i]",
    "input[name*=login i]",
    "input[name*=email i]",
    "input[autocomplete=username]",
    "input[type=text]",
]
