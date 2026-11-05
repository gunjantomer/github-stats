#!/usr/bin/python3

import asyncio
import os
import re
from typing import Dict, List, Tuple

import aiohttp

from github_stats import Stats


################################################################################
# Helper Functions
################################################################################


def generate_output_folder() -> None:
    """
    Create the output folder if it does not already exist
    """
    if not os.path.isdir("generated"):
        os.mkdir("generated")


def flatten_calendar(
    weeks: List[List[Dict[str, object]]]
) -> List[Tuple[str, int]]:
    """
    Turn the grouped contribution calendar into a flat, chronological list of
    (date, contribution_count) pairs.
    :param weeks: list of weeks, each a list of {date, contributionCount} days
    :return: ordered list of (date, count) tuples
    """
    days: List[Tuple[str, int]] = []
    for week in weeks:
        for day in week:
            days.append(
                (
                    str(day.get("date", "")),
                    int(day.get("contributionCount", 0) or 0),
                )
            )
    return days


def compute_streak(days: List[Tuple[str, int]]) -> Tuple[int, int]:
    """
    Compute the current and longest contribution streaks from daily counts.
    The current streak allows a single day of grace for the in-progress current
    day, matching how GitHub presents streaks (a gap older than one day resets
    it).
    :param days: ordered (date, count) pairs
    :return: (current_streak, longest_streak) in days
    """
    if not days:
        return (0, 0)

    longest = 0
    run = 0
    for _, count in days:
        if count > 0:
            run += 1
            if run > longest:
                longest = run
        else:
            run = 0

    index = len(days) - 1
    # Grace for the current day, which may not have a contribution yet.
    if index >= 0 and days[index][1] == 0:
        index -= 1

    current = 0
    while index >= 0 and days[index][1] > 0:
        current += 1
        index -= 1

    return (current, longest)


def level_for(count: int) -> int:
    """
    Map a daily contribution count to a GitHub-style intensity level (0-4).
    :param count: contributions on a given day
    :return: intensity level, 0 for none up to 4 for the busiest days
    """
    if count <= 0:
        return 0
    if count <= 2:
        return 1
    if count <= 5:
        return 2
    if count <= 9:
        return 3
    return 4


################################################################################
# Individual Image Generation Functions
################################################################################


async def generate_overview(s: Stats) -> None:
    """
    Generate an SVG badge with summary statistics
    :param s: Represents user's GitHub statistics
    """
    with open("templates/overview.svg", "r") as f:
        output = f.read()

    output = re.sub("{{ name }}", await s.name, output)
    output = re.sub("{{ stars }}", f"{await s.stargazers:,}", output)
    output = re.sub("{{ forks }}", f"{await s.forks:,}", output)
    output = re.sub("{{ contributions }}", f"{await s.total_contributions:,}", output)
    changed = (await s.lines_changed)[0] + (await s.lines_changed)[1]
    output = re.sub("{{ lines_changed }}", f"{changed:,}", output)
    output = re.sub("{{ views }}", f"{await s.views:,}", output)
    output = re.sub("{{ repos }}", f"{len(await s.repos):,}", output)

    generate_output_folder()
    with open("generated/overview.svg", "w") as f:
        f.write(output)


async def generate_languages(s: Stats) -> None:
    """
    Generate an SVG badge with summary languages used
    :param s: Represents user's GitHub statistics
    """
    with open("templates/languages.svg", "r") as f:
        output = f.read()

    progress = ""
    lang_list = ""
    sorted_languages = sorted(
        (await s.languages).items(), reverse=True, key=lambda t: t[1].get("size")
    )
    delay_between = 150
    for i, (lang, data) in enumerate(sorted_languages):
        color = data.get("color")
        color = color if color is not None else "#000000"
        progress += (
            f'<span style="background-color: {color};'
            f'width: {data.get("prop", 0):0.3f}%;" '
            f'class="progress-item"></span>'
        )
        lang_list += f"""
<li style="animation-delay: {i * delay_between}ms;">
<svg xmlns="http://www.w3.org/2000/svg" class="octicon" style="fill:{color};"
viewBox="0 0 16 16" version="1.1" width="16" height="16"><path
fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8z"></path></svg>
<span class="lang">{lang}</span>
<span class="percent">{data.get("prop", 0):0.2f}%</span>
</li>

"""

    output = re.sub(r"{{ progress }}", progress, output)
    output = re.sub(r"{{ lang_list }}", lang_list, output)

    generate_output_folder()
    with open("generated/languages.svg", "w") as f:
        f.write(output)


async def generate_streak(s: Stats) -> None:
    """
    Generate an SVG badge with contribution streak statistics.
    :param s: Represents user's GitHub statistics
    """
    with open("templates/streak.svg", "r") as f:
        output = f.read()

    days = flatten_calendar(await s.contributions_calendar)
    current, longest = compute_streak(days)
    year_total = sum(count for _, count in days)

    year = ""
    for date, _ in reversed(days):
        if date:
            year = date[:4]
            break

    output = re.sub("{{ current }}", f"{current:,}", output)
    output = re.sub("{{ longest }}", f"{longest:,}", output)
    output = re.sub("{{ year_total }}", f"{year_total:,}", output)
    output = re.sub("{{ year }}", year or "this year", output)

    generate_output_folder()
    with open("generated/streak.svg", "w") as f:
        f.write(output)


async def generate_pullrequests(s: Stats) -> None:
    """
    Generate an SVG badge summarising pull-request impact: pull requests
    opened, merged, and the resulting merge rate. Uses search data fetched by
    Stats rather than raw line counts, which no longer reflect effort in the
    age of AI-generated code.
    :param s: Represents user's GitHub statistics
    """
    with open("templates/pullrequests.svg", "r") as f:
        output = f.read()

    opened = await s.prs_opened
    merged = await s.prs_merged

    if opened:
        rate = round(100 * merged / opened)
        big = f"{opened:,}"
        unit = "pull requests opened"
        line1 = f'<tspan class="value merged">{merged:,}</tspan> merged into main'
        line2 = f'<tspan class="value rate">{rate}%</tspan> merge rate'
    else:
        # Search returned nothing (missing repo scope, private repos, or a
        # transient failure). Fall back to GraphQL viewer contributions, which
        # include private repositories, so the card never shows a misleading 0.
        opened_c = await s.pr_contributions
        commits = await s.commit_contributions
        repos = await s.repository_contributions
        big = f"{opened_c:,}"
        unit = "pull requests opened (last year)"
        line1 = f'<tspan class="value">{commits:,}</tspan> commits contributed (last year)'
        line2 = f'<tspan class="value">{repos:,}</tspan> repositories created (last year)'

    output = re.sub("{{ big }}", big, output)
    output = re.sub("{{ unit }}", unit, output)
    output = re.sub("{{ line1 }}", line1, output)
    output = re.sub("{{ line2 }}", line2, output)

    generate_output_folder()
    with open("generated/pullrequests.svg", "w") as f:
        f.write(output)


async def generate_contributions(s: Stats) -> None:
    """
    Generate an SVG contribution graph (heatmap) for the trailing year.
    :param s: Represents user's GitHub statistics
    """
    with open("templates/contributions.svg", "r") as f:
        output = f.read()

    weeks = await s.contributions_calendar

    cell = 11
    gap = 3
    step = cell + gap
    grid_left = 18
    grid_top = 36

    cells = ""
    month_labels = ""
    last_month = None
    for wi, week in enumerate(weeks):
        for di, day in enumerate(week):
            x = grid_left + wi * step
            y = grid_top + di * step
            level = level_for(int(day.get("contributionCount", 0) or 0))
            cells += (
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
                f'rx="2" ry="2" class="cell level{level}"/>\n'
            )
        # Month label above the first column of each new month.
        first_date = str(week[0].get("date", "")) if week else ""
        month = first_date[5:7] if first_date else ""
        if month and month != last_month:
            month_labels += (
                f'<text x="{grid_left + wi * step}" y="{grid_top - 6}" class="month">'
                f"{_month_name(int(month))}</text>\n"
            )
            last_month = month

    width = grid_left + len(weeks) * step + 12
    height = grid_top + 7 * step + 30
    # Never narrower than the title + legend need, regardless of data size.
    if width < 280:
        width = 280

    legend = f'<text x="{grid_left}" y="{height - 14}" class="legend">Less</text>'
    lx = grid_left + 36
    for level in range(5):
        legend += (
            f'<rect x="{lx}" y="{height - 24}" width="{cell}" height="{cell}" '
            f'class="cell level{level}"/>'
        )
        lx += step
    legend += f'<text x="{lx + 4}" y="{height - 14}" class="legend">More</text>'

    output = re.sub("{{ width }}", str(width), output)
    output = re.sub("{{ height }}", str(height), output)
    output = re.sub("{{ bw }}", str(width - 10), output)
    output = re.sub("{{ bh }}", str(height - 10), output)
    output = re.sub("{{ cells }}", cells, output)
    output = re.sub("{{ month_labels }}", month_labels, output)
    output = re.sub("{{ legend }}", legend, output)

    generate_output_folder()
    with open("generated/contributions.svg", "w") as f:
        f.write(output)


_MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


def _month_name(number: int) -> str:
    """
    :param number: month number, 1-12
    :return: three-letter English month abbreviation
    """
    if 1 <= number <= 12:
        return _MONTHS[number - 1]
    return ""


################################################################################
# Main Function
################################################################################


async def main() -> None:
    """
    Generate all badges
    """
    access_token = os.getenv("ACCESS_TOKEN")
    if not access_token:
        # access_token = os.getenv("GITHUB_TOKEN")
        raise Exception("A personal access token is required to proceed!")
    user = os.getenv("GITHUB_ACTOR")
    if user is None:
        raise RuntimeError("Environment variable GITHUB_ACTOR must be set.")
    exclude_repos = os.getenv("EXCLUDED")
    excluded_repos = (
        {x.strip() for x in exclude_repos.split(",")} if exclude_repos else None
    )
    exclude_langs = os.getenv("EXCLUDED_LANGS")
    excluded_langs = (
        {x.strip() for x in exclude_langs.split(",")} if exclude_langs else None
    )
    # Convert a truthy value to a Boolean
    raw_ignore_forked_repos = os.getenv("EXCLUDE_FORKED_REPOS")
    ignore_forked_repos = (
        not not raw_ignore_forked_repos
        and raw_ignore_forked_repos.strip().lower() != "false"
    )
    async with aiohttp.ClientSession() as session:
        s = Stats(
            user,
            access_token,
            session,
            exclude_repos=excluded_repos,
            exclude_langs=excluded_langs,
            ignore_forked_repos=ignore_forked_repos,
        )
        # Fail loudly before touching any files: an expired token used to
        # overwrite previously good images with zeros. Aborting here keeps the
        # last successful images committed.
        await s.preflight()

        await asyncio.gather(
            generate_languages(s),
            generate_overview(s),
            generate_streak(s),
            generate_pullrequests(s),
            generate_contributions(s),
        )


if __name__ == "__main__":
    asyncio.run(main())
