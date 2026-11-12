# Contributing to Nook

Thanks for helping. Nook stays small on purpose, so please read this before you open a pull request.

## Reporting a bug

Open an [issue](https://github.com/Liyan-Shanvel/Nook/issues/new/choose) with:

- your Nook version (Settings, bottom of the page) and your Windows version
- what you did, what you expected, and what happened
- a screenshot if it is about how something looks

## Suggesting a feature

Open a feature request and say what problem it solves for you. Nook only adds things people use every day, so a clear "why" matters more than a detailed "how".

## Pull requests

1. Open an issue first for anything bigger than a small fix, so we agree on it before you spend time.
2. Keep the change focused: one fix or feature per pull request.
3. Run the tests: `py -m pytest -q tests`. They must all pass.
4. If you change anything in `ui/`, bump the `?v=` number in `ui/index.html` so the app does not show a cached copy.
5. Match the look: dark, calm, monochrome. Colour only when it means something (green = done, red = distracted).

## Ground rules

- Your data stays on your PC. No change may send tasks, habits or tracked apps anywhere.
- No ads, no tracking, no accounts beyond the optional Google sign-in.
- Tests never call real Google, the real Startup folder, or the updater.

By contributing, you agree that your contribution is licensed under the same [license](LICENSE) as the project.
