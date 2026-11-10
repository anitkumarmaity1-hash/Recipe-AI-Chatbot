# Publishing the prebuilt data asset

The installer expects this exact release asset:

`https://github.com/anitkumarmaity1-hash/Recipe-AI-Chatbot/releases/download/data-v1/nosh_data.zip`

A repository checkout cannot create a GitHub Release by itself. The repository therefore includes
`.github/workflows/publish-prebuilt.yml` to create the release asset in GitHub using the repository's
`GITHUB_TOKEN`.

## One-time publication

1. Push the project, including `.github/workflows/publish-prebuilt.yml`, to the public GitHub repo.
2. Open **Actions → Publish prebuilt recipe data**.
3. Select **Run workflow** and keep the release tag as `data-v1`.
4. Wait for the workflow job to complete successfully. It downloads the three source JSON files,
   builds DuckDB, BM25 and FAISS, packages them as `dist/nosh_data.zip`, and creates or updates the
   `data-v1` release asset.
5. Verify the `nosh_data.zip` asset appears on the repository's Releases page.
6. On a fresh clone, run `python scripts/fetch_prebuilt.py`.

The workflow has `contents: write` permission so it can publish the release. It does not commit the
raw dataset, generated database, or indexes into Git history. The build can take a long time because
ingredient parsing and semantic embedding are performed over the complete dataset.

## Local alternative

When GitHub Actions is not available, follow the full data build in `README.md` and then run:

```powershell
python scripts/pack_prebuilt.py
```

This creates `dist/nosh_data.zip`. Publishing that file manually as the `data-v1` release asset also
satisfies the download URL expected by `scripts/fetch_prebuilt.py`.
