# Security policy

## Reporting a vulnerability

Please do not open a public issue for a credential leak, data exposure, or vulnerability that could cause unauthorized AssemblyAI API use. Contact the repository owner privately through GitHub security advisories or a private GitHub contact channel.

## Credential policy

`ASSEMBLYAI_API_KEY` is a secret. Never include it in issues, pull requests, fixtures, screenshots, shell history, or releases. Before publishing, run:

```sh
git grep -nEi 'ASSEMBLYAI_API_KEY=.{12,}|[a-f0-9]{32}'
```

The command should return only the placeholder in `.env.example` and documentation examples—not a credential. If a key is exposed, rotate it in the AssemblyAI dashboard immediately.
