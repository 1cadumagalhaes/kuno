# GitHub Pages deployment

`.github/workflows/pages.yml` deploys the static `site/` directory on pushes to `main` and on manual dispatch. It checks that the Portuguese and English page structures stay aligned, uploads `site/` as the Pages artifact, then deploys it. No build or generated files are needed.

## One-time GitHub setup

In the repository, open **Settings → Pages** and set **Build and deployment → Source** to **GitHub Actions**. The custom domain `cadumagalhaes.dev` belongs to the account's user site; it is inherited at the domain level, not configured as Kuno's per-repository custom domain. Do not add a Kuno `CNAME` for the root domain.

The expected URLs are `https://cadumagalhaes.dev/kuno/` (Portuguese) and `https://cadumagalhaes.dev/kuno/en/` (English). Project Pages sites are served below `/<repo>/`; relative asset links and the pages' canonical/hreflang/Open Graph URLs already use that path.

## Verify a deployment

After enabling Pages, merge to `main` or run **Actions → Deploy GitHub Pages → Run workflow**. Confirm the run passes the parity check and deploy job, then open both URLs and check representative CSS, JS, SVG and PNG assets. The deploy job's `github-pages` environment URL is another useful check. This setup has not been published from this workspace.

## Path-specific notes

- `site/robots.txt` deploys as `/kuno/robots.txt`; crawlers consult `/robots.txt` at the host root. That root file is owned by the personal user site, so coordinate any Kuno-specific crawler rules with its maintainer rather than expecting this project deployment to change it.
- `site/llms.txt` is available at `/kuno/llms.txt` and its linked page URLs are path-qualified. It is usable when linked directly, but is not the domain-root `/llms.txt` convention.
- Keep the canonical trailing slashes (`/kuno/` and `/kuno/en/`). GitHub Pages serves directory index pages; check the slashless `/kuno` and `/kuno/en` responses after deployment rather than relying on an assumed redirect.
- `.nojekyll` is unnecessary here: the Actions Pages artifact is deployed as static content without a Jekyll build, and the site has no Jekyll/underscore-prefixed content to preserve.
- OG cards are committed at fixed names (`assets/og-pt.png`, `assets/og-en.png`). If regenerated content appears stale after deploy, allow for browser/CDN caching; changing the filename and its references is the reliable cache-bust.
