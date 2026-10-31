# Menlo Park Field Finder

A free website showing open times at City of Menlo Park athletic fields for the next 8 weeks.
GitHub Pages hosts the page, and a GitHub Action refreshes the data every 3 hours.

## What's in here

- `index.html`: the website
- `data.json`: the open times the page shows (updated automatically)
- `scrape.py` and `server.py`: the script that reads the city's booking site
- `.github/workflows/refresh.yml`: runs the script on a schedule

## Set it up (about 5 minutes)

1. Sign in at https://github.com and click **New repository** (the **+** in the top right).
   Name it `field-finder`, set it to **Public**, and click **Create repository**.
2. On the new repository's page, click **uploading an existing file**.
   Drag in everything from this folder, **including the hidden `.github` folder**.
   On a Mac, press Cmd+Shift+. in Finder to show hidden folders.
   Click **Commit changes**.
   If the `.github` folder won't upload, click **Add file > Create new file**, type
   `.github/workflows/refresh.yml` as the name, paste in that file's contents and commit.
3. Go to **Settings > Pages**. Under "Build and deployment", set Source to
   **Deploy from a branch**, Branch to **main** and folder to **/ (root)**, then click **Save**.
4. Go to **Settings > Actions > General**. Under "Workflow permissions", choose
   **Read and write permissions** and click **Save**.
5. Go to the **Actions** tab. If it asks, click to enable workflows. Open
   **Refresh field data** and click **Run workflow** to fetch fresh data now.

After a minute or two your site is live at
`https://<your-github-username>.github.io/field-finder/`.
The link also appears at the top of **Settings > Pages**.

## Good to know

- Data refreshes every 3 hours. To refresh right away, run the workflow from the Actions tab.
- GitHub pauses scheduled workflows in repositories with no activity for 60 days. If the
  "Updated" time on the page stops moving, open the Actions tab and re-enable the workflow.
- A free GitHub Pages site needs a public repository, so anyone with the link can see the page.
