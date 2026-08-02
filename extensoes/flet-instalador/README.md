# flet-instalador
FletInstalador control for Flet

## Installation

Add dependency to `pyproject.toml` of your Flet app:

* **Git dependency**

Link to git repository:

```
dependencies = [
  "flet-instalador @ git+https://github.com/MyGithubAccount/flet-instalador",
  "flet>=0.85.3",
]
```

* **uv/pip dependency**

If the package is published on pypi.org:

```
dependencies = [
  "flet-instalador",
  "flet>=0.85.3",
]
```

Build your app:
```
flet build macos -v
```

## Documentation

[Link to documentation](https://MyGithubAccount.github.io/flet-instalador/)
