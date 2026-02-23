# tony README

CC Github task manager

## 構成

```
リポジトリディレクトリ
| .gitignore
| .pre-commit-config.yaml
| Makefile
| pyproject.toml
| LICENCE
| README.md
|
└─── .circleci
|    |   config.yml
|
└─── data (データ用ディレクトリ)
|    .gitkeep
|
└─── tests
|    |   __init__.py
|    |   test_tony.py
|
└─── tony
|    |   __init__.py        
```

## Local Development

Python: 3.14

> Requires [uv](https://docs.astral.sh/uv/guides/install-python/) for dependency management


### 開発環境のインストール

1. `pre-commit` のフックをインストール (_ruff_):

    > [pre-commit](https://pre-commit.com/#install) がすでにインストールされていることを前提としています。

    ```bash
    pre-commit install
    ```

2. The following command installs project and development dependencies:

    ```bash
    uv sync 
    ```

### 新パッケージの追加

パッケージを追加するには、プロジェクトのルートディレクトリから次のコマンドを実行します:
```
uv add {PACKAGE TO INSTALL}
```

 ## コードチェックを実行
 
 ```
 uv run poe check
 ```

タイプチェックを実行：
```
uv run poe typecheck
```

## テストケースを実行

This project uses [pytest](https://docs.pytest.org/en/latest/contents.html) for running testcases.

テストケースは、`tests` ディレクトリにおいて追加してきます.

テストケースを実行するには、次のコマンドを実行します:
```
pytest -v
# または、親ディレクトリから
uv run poe test
```

## パッケージをビルド

`main`ブランチにブランチがマージされると、パッケージがビルドされて、Githubのリリースにアップロードされます。

手動にビルドする場合は、次のコマンドを実行します:

> `dist`ディレクトリにビルドされたパッケージが作成されます。
 
```
uv build
```
