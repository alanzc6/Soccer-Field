# Field Finder

A free website that shows open times at city athletic fields, for any city whose
field rentals are booked through PerfectMind or ActiveNet. GitHub Pages hosts it, and a
GitHub Action refreshes the data every 3 hours.

## What's in here

- `index.html`: the home page, with the list of cities and an "Add a city" form
- `city.html`: the field finder for one city (opened from the home page)
- `cities.json`: the list of cities
- `data/`: open times for each city (updated automatically)
- `scrape.py`, `server.py` (PerfectMind) and `activenet.py` (ActiveNet): the script that reads each city's booking site
- `.github/workflows/refresh.yml`: runs the script every 3 hours, and whenever `cities.json` changes

## Adding a city

Use the "Add a city" form on the home page. It checks the link, then gives you a
snippet to paste into `cities.json` on GitHub. After you commit, the new city's
data loads automatically in about two minutes.

A city entry looks like this:

```json
{
  "id": "menlo-park",
  "name": "Menlo Park",
  "state": "CA",
  "bookingLink": "https://cityofmenlopark.perfectmind.com/26116/Clients/BookMe4FacilityList/List?widgetId=...&calendarId=..."
}
```

For PerfectMind, the booking link must be the city's facility list page, the one
that lists all the fields, with `widgetId` and `calendarId` in it. For ActiveNet,
any link on the city's `activecommunities.com` site works, for example
`https://anc.apm.activecommunities.com/sanjoseparksandrec/reservation/search`.

## Setting up from scratch

1. Create a **public** GitHub repository and upload everything in this folder,
   including the hidden `.github` folder.
2. **Settings > Pages**: Deploy from a branch, **main**, **/ (root)**, Save.
3. **Settings > Actions > General**: Workflow permissions **Read and write**, Save.
4. **Actions** tab: run **Refresh field data** once.

## Good to know

- GitHub pauses scheduled workflows in repositories with no activity for 60 days.
  If the "updated" times stop moving, re-enable the workflow on the Actions tab.
- Cities that use a different booking system (not PerfectMind or ActiveNet) won't work without new code.
