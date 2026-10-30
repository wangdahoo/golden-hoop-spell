# Task: Add find_user

Extend `users.py` with `find_user(users, email)`:

- `users` is an iterable of dictionaries containing an `"email"` key.
- Return the first dictionary whose email is an exact case-insensitive match for `email`.
- Return `None` when there is no match or no match is found.
- Do not mutate `users` or the dictionaries.
- Keep the implementation standard-library only and do not add command-line behavior.
