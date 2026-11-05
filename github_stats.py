#!/usr/bin/python3

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple, Any, cast

import aiohttp
import requests


# Language colors used by the languages card. The REST /languages endpoint no
# longer reports colors, and fine-grained tokens cannot read the GraphQL
# language color field, so colors are mapped from this (GitHub linguist) table.
# Unknown languages fall back to the card's default color.
_LANGUAGE_COLORS = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "C++": "#f34b7d",
    "C": "#555555",
    "C#": "#178600",
    "Go": "#00ADD8",
    "Java": "#b07219",
    "Kotlin": "#A13D9D",
    "Swift": "#F05138",
    "Rust": "#dea584",
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "Scala": "#c22d40",
    "Shell": "#89e051",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "SCSS": "#c6538c",
    "Jupyter Notebook": "#DA5B0B",
    "MATLAB": "#e16737",
    "R": "#198CE7",
    "Dart": "#00B4AB",
    "Vue": "#41b883",
    "Svelte": "#ff3e00",
    "Markdown": "#df5f43",
    "Makefile": "#427819",
    "CMake": "#84428f",
    "TeX": "#3D6117",
    "Lua": "#000080",
    "Perl": "#9e3373",
    "Haskell": "#5e5086",
    "Elixir": "#6e4a7e",
    "Objective-C": "#43abda",
    "Groovy": "#e17b44",
    "Solidity": "#AA6746",
    "CUDA": "#0AEf09",
    "GLSL": "#563d7c",
    "YAML": "#121512",
    "JSON": "#0064ff",
    "Dockerfile": "#384d54",
    "Batchfile": "#519842",
    "PowerShell": "#012456",
    "GDScript": "#608060",
    "Zig": "#ec915c",
    "Nix": "#9e91ca",
    "Verilog": "#b2a79f",
    "VHDL": "#adb3cb",
}


###############################################################################
# Main Classes
###############################################################################


class Queries(object):
    """
    Class with functions to query the GitHub GraphQL (v4) API and the REST (v3)
    API. Also includes functions to dynamically generate GraphQL queries.
    """

    def __init__(
        self,
        username: str,
        access_token: str,
        session: aiohttp.ClientSession,
        max_connections: int = 10,
    ):
        self.username = username
        self.access_token = access_token
        self.session = session
        self.semaphore = asyncio.Semaphore(max_connections)

    async def query(self, generated_query: str) -> Dict:
        """
        Make a request to the GraphQL API using the authentication token from
        the environment
        :param generated_query: string query to be sent to the API
        :return: decoded GraphQL JSON output
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }
        try:
            async with self.semaphore:
                r_async = await self.session.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={"query": generated_query},
                )
            result = await r_async.json()
            if result is not None:
                return result
        except:
            print("aiohttp failed for GraphQL query")
            # Fall back on non-async requests
            async with self.semaphore:
                r_requests = requests.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={"query": generated_query},
                )
                result = r_requests.json()
                if result is not None:
                    return result
        return dict()

    async def query_rest(self, path: str, params: Optional[Dict] = None) -> Dict:
        """
        Make a request to the REST API
        :param path: API path to query
        :param params: Query parameters to be passed to the API
        :return: deserialized REST JSON output
        """

        for _ in range(60):
            headers = {
                "Authorization": f"token {self.access_token}",
            }
            if params is None:
                params = dict()
            if path.startswith("/"):
                path = path[1:]
            try:
                async with self.semaphore:
                    r_async = await self.session.get(
                        f"https://api.github.com/{path}",
                        headers=headers,
                        params=tuple(params.items()),
                    )
                if r_async.status == 202:
                    # print(f"{path} returned 202. Retrying...")
                    print(f"A path returned 202. Retrying...")
                    await asyncio.sleep(2)
                    continue

                result = await r_async.json()
                if result is not None:
                    return result
            except:
                print("aiohttp failed for rest query")
                # Fall back on non-async requests
                async with self.semaphore:
                    r_requests = requests.get(
                        f"https://api.github.com/{path}",
                        headers=headers,
                        params=tuple(params.items()),
                    )
                    if r_requests.status_code == 202:
                        print(f"A path returned 202. Retrying...")
                        await asyncio.sleep(2)
                        continue
                    elif r_requests.status_code == 200:
                        return r_requests.json()
        # print(f"There were too many 202s. Data for {path} will be incomplete.")
        print("There were too many 202s. Data for this repository will be incomplete.")
        return dict()

    @staticmethod
    def contrib_years() -> str:
        """
        :return: GraphQL query to get all years the user has been a contributor
        """
        return """
query {
  viewer {
    contributionsCollection {
      contributionYears
    }
  }
}
"""

    @staticmethod
    def contribs_by_year(year: str) -> str:
        """
        :param year: year to query for
        :return: portion of a GraphQL query with desired info for a given year
        """
        return f"""
    year{year}: contributionsCollection(
        from: "{year}-01-01T00:00:00Z",
        to: "{int(year) + 1}-01-01T00:00:00Z"
    ) {{
      contributionCalendar {{
        totalContributions
      }}
    }}
"""

    @classmethod
    def all_contribs(cls, years: List[str]) -> str:
        """
        :param years: list of years to get contributions for
        :return: query to retrieve contribution information for all user years
        """
        by_years = "\n".join(map(cls.contribs_by_year, years))
        return f"""
query {{
  viewer {{
    {by_years}
  }}
}}
"""

    @staticmethod
    def viewer_login() -> str:
        """
        Minimal query used to verify that the access token is valid and scoped
        correctly. Returns the viewer login, or nothing when the token is
        missing, expired, or lacks the required scopes.
        :return: GraphQL query returning only the viewer login
        """
        return """
query {
  viewer {
    login
  }
}
"""

    @staticmethod
    def contributions_calendar(from_date: str, to_date: str) -> str:
        """
        Fetch the daily contribution calendar for a date range, which powers
        the streak and contribution-graph cards.
        :param from_date: ISO-8601 start of the range
        :param to_date: ISO-8601 end of the range
        :return: GraphQL query for the contribution calendar in that range
        """
        return f"""
query {{
  viewer {{
    contributionsCollection(from: "{from_date}", to: "{to_date}") {{
      contributionCalendar {{
        totalContributions
        weeks {{
          contributionDays {{
            contributionCount
            date
          }}
        }}
      }}
    }}
  }}
}}
"""


class Stats(object):
    """
    Retrieve and store statistics about GitHub usage.
    """

    def __init__(
        self,
        username: str,
        access_token: str,
        session: aiohttp.ClientSession,
        exclude_repos: Optional[Set] = None,
        exclude_langs: Optional[Set] = None,
        ignore_forked_repos: bool = False,
    ):
        self.username = username
        self._ignore_forked_repos = ignore_forked_repos
        self._exclude_repos = set() if exclude_repos is None else exclude_repos
        self._exclude_langs = set() if exclude_langs is None else exclude_langs
        self.queries = Queries(username, access_token, session)

        self._name: Optional[str] = None
        self._stargazers: Optional[int] = None
        self._forks: Optional[int] = None
        self._total_contributions: Optional[int] = None
        self._languages: Optional[Dict[str, Any]] = None
        self._repos: Optional[Set[str]] = None
        self._lines_changed: Optional[Tuple[int, int]] = None
        self._views: Optional[int] = None
        self._prs_opened: Optional[int] = None
        self._prs_merged: Optional[int] = None
        self._contrib: Optional[Dict[str, int]] = None
        self._calendar: Optional[List[List[Dict[str, Any]]]] = None

    async def to_str(self) -> str:
        """
        :return: summary of all available statistics
        """
        languages = await self.languages_proportional
        formatted_languages = "\n  - ".join(
            [f"{k}: {v:0.4f}%" for k, v in languages.items()]
        )
        lines_changed = await self.lines_changed
        return f"""Name: {await self.name}
Stargazers: {await self.stargazers:,}
Forks: {await self.forks:,}
All-time contributions: {await self.total_contributions:,}
Repositories with contributions: {len(await self.repos)}
Lines of code added: {lines_changed[0]:,}
Lines of code deleted: {lines_changed[1]:,}
Lines of code changed: {lines_changed[0] + lines_changed[1]:,}
Project page views: {await self.views:,}
Languages:
  - {formatted_languages}"""

    async def get_stats(self) -> None:
        """
        Get lots of summary statistics. Sets many attributes.

        Fine-grained personal access tokens cannot resolve the GraphQL
        repository fields (viewer connections or ``repository()``), which is
        why the language, stars, forks and repository-count cards came back
        empty even though contributions and pull requests populated. This
        therefore builds the repository set and the language / star / fork
        totals from the REST API (which fine-grained tokens *do* serve,
        including private repositories), using GraphQL only for the viewer
        name and the best-effort contributed-repository list.
        """
        self._stargazers = 0
        self._forks = 0
        self._languages = dict()
        self._repos = set()

        name_query = await self.queries.query("{ viewer { name login } }")
        viewer = (
            name_query.get("data", {}).get("viewer", {})
            if isinstance(name_query, dict)
            else {}
        )
        self._name = viewer.get("name") or viewer.get("login") or "No Name"

        exclude_langs_lower = {x.lower() for x in self._exclude_langs}

        for full, stars, forks, is_fork in await self._collect_repos():
            if is_fork and self._ignore_forked_repos:
                continue
            if full in self._repos or full in self._exclude_repos:
                continue
            self._repos.add(full)
            self._stargazers += stars
            self._forks += forks

        # Languages come from the REST API (fine-grained tokens serve it);
        # colors come from an embedded map, since the REST /languages endpoint
        # no longer reports them.
        lang_results = await asyncio.gather(
            *[
                self.queries.query_rest(f"/repos/{full}/languages")
                for full in self._repos
            ],
            return_exceptions=True,
        )
        for langs in lang_results:
            if not isinstance(langs, dict):
                continue
            for lname, size in langs.items():
                if lname.lower() in exclude_langs_lower:
                    continue
                if lname in self._languages:
                    self._languages[lname]["size"] += size
                    self._languages[lname]["occurrences"] += 1
                else:
                    self._languages[lname] = {
                        "size": size,
                        "occurrences": 1,
                        "color": _LANGUAGE_COLORS.get(lname),
                    }

        # TODO: Improve languages to scale by number of contributions to
        #       specific filetypes
        langs_total = sum([v.get("size", 0) for v in self._languages.values()])
        if langs_total:
            for k, v in self._languages.items():
                v["prop"] = 100 * (v.get("size", 0) / langs_total)

    async def _collect_repos(self) -> list:
        """
        :return: list of ``(full_name, stargazers, forks, is_fork)`` tuples
            built from the owner's repositories via REST, plus viewer-
            contributed repositories (best-effort GraphQL) that the owner does
            not already own.
        """
        repos = []
        owned_names = set()
        for repo in await self._created_repos():
            full = repo.get("full_name")
            if not full:
                continue
            owned_names.add(full)
            repos.append(
                (
                    full,
                    repo.get("stargazers_count", 0),
                    repo.get("forks_count", 0),
                    bool(repo.get("fork")),
                )
            )
        for name in await self._contributed_repos():
            if name in owned_names:
                continue
            obj = await self.queries.query_rest(f"/repos/{name}")
            if isinstance(obj, dict) and obj.get("full_name"):
                repos.append(
                    (
                        obj["full_name"],
                        obj.get("stargazers_count", 0),
                        obj.get("forks_count", 0),
                        bool(obj.get("fork")),
                    )
                )
        return repos

    async def _contributed_repos(self) -> set:
        """
        :return: repositories the viewer contributed to (commits + pull
            requests). Viewer-scoped, so it works with fine-grained tokens and
            includes private repositories.
        """
        raw = await self.queries.query(
            "{ viewer { contributionsCollection {"
            " commitContributionsByRepository(maxRepositories: 100)"
            " { repository { nameWithOwner } }"
            " pullRequestContributionsByRepository(maxRepositories: 100)"
            " { repository { nameWithOwner } }"
            " } } }"
        )
        collection = (
            raw.get("data", {}).get("viewer", {}).get("contributionsCollection", {})
            if isinstance(raw, dict)
            else {}
        )
        names = set()
        for key in (
            "commitContributionsByRepository",
            "pullRequestContributionsByRepository",
        ):
            for entry in collection.get(key, []):
                name = entry.get("repository", {}).get("nameWithOwner")
                if name:
                    names.add(name)
        return names

    async def _created_repos(self) -> list:
        """
        :return: repository objects the owner owns, via the REST API (which
            fine-grained tokens serve, including private repositories), each
            carrying full_name, stargazers_count, forks_count and fork.
        """
        repos = []
        page = 1
        while True:
            raw = await self.queries.query_rest(
                "/user/repos",
                params={"per_page": 100, "type": "owner", "page": page},
            )
            if not isinstance(raw, list) or not raw:
                break
            repos += [repo for repo in raw if isinstance(repo, dict)]
            if len(raw) < 100:
                break
            page += 1
        return repos

    @property
    async def name(self) -> str:
        """
        :return: GitHub user's name (e.g., Jacob Strieb)
        """
        if self._name is not None:
            return self._name
        await self.get_stats()
        assert self._name is not None
        return self._name

    @property
    async def stargazers(self) -> int:
        """
        :return: total number of stargazers on user's repos
        """
        if self._stargazers is not None:
            return self._stargazers
        await self.get_stats()
        assert self._stargazers is not None
        return self._stargazers

    @property
    async def forks(self) -> int:
        """
        :return: total number of forks on user's repos
        """
        if self._forks is not None:
            return self._forks
        await self.get_stats()
        assert self._forks is not None
        return self._forks

    @property
    async def languages(self) -> Dict:
        """
        :return: summary of languages used by the user
        """
        if self._languages is not None:
            return self._languages
        await self.get_stats()
        assert self._languages is not None
        return self._languages

    @property
    async def languages_proportional(self) -> Dict:
        """
        :return: summary of languages used by the user, with proportional usage
        """
        if self._languages is None:
            await self.get_stats()
            assert self._languages is not None

        return {k: v.get("prop", 0) for (k, v) in self._languages.items()}

    @property
    async def repos(self) -> Set[str]:
        """
        :return: list of names of user's repos
        """
        if self._repos is not None:
            return self._repos
        await self.get_stats()
        assert self._repos is not None
        return self._repos

    @property
    async def total_contributions(self) -> int:
        """
        :return: count of user's total contributions as defined by GitHub
        """
        if self._total_contributions is not None:
            return self._total_contributions

        self._total_contributions = 0
        years = (
            (await self.queries.query(Queries.contrib_years()))
            .get("data", {})
            .get("viewer", {})
            .get("contributionsCollection", {})
            .get("contributionYears", [])
        )
        by_year = (
            (await self.queries.query(Queries.all_contribs(years)))
            .get("data", {})
            .get("viewer", {})
            .values()
        )
        for year in by_year:
            self._total_contributions += year.get("contributionCalendar", {}).get(
                "totalContributions", 0
            )
        return cast(int, self._total_contributions)

    @property
    async def lines_changed(self) -> Tuple[int, int]:
        """
        :return: count of total lines added, removed, or modified by the user
        """
        if self._lines_changed is not None:
            return self._lines_changed

        repos = await self.repos
        # GitHub computes contributor stats on demand and answers HTTP 202
        # until the numbers are ready. Query every repo concurrently so the
        # step is bounded by the slowest repo — GitHub caches the result for
        # the next run — instead of summing up to ~2 minutes of per-repo
        # waiting across all of them, which used to time out and render 0.
        results = await asyncio.gather(
            *[self.queries.query_rest(f"/repos/{repo}/stats/contributors") for repo in repos],
            return_exceptions=True,
        )

        additions = 0
        deletions = 0
        for r in results:
            if not isinstance(r, list):
                # A repo that timed out on 202 yields {} (not a list): skip it
                # rather than treating the placeholder as contributor data.
                continue
            for author_obj in r:
                # Handle malformed response from the API by skipping this repo
                if not isinstance(author_obj, dict) or not isinstance(
                    author_obj.get("author", {}), dict
                ):
                    continue
                author = author_obj.get("author", {}).get("login", "")
                if author != self.username:
                    continue

                for week in author_obj.get("weeks", []):
                    additions += week.get("a", 0)
                    deletions += week.get("d", 0)

        self._lines_changed = (additions, deletions)
        return self._lines_changed

    @property
    async def views(self) -> int:
        """
        Note: only returns views for the last 14 days (as-per GitHub API)
        :return: total number of page views the user's projects have received
        """
        if self._views is not None:
            return self._views

        repos = await self.repos
        # Same on-demand HTTP 202 behaviour as contributor stats; fetch
        # concurrently so slow repos don't push the step past its budget.
        # Repos the user does not own return 403 and contribute nothing.
        results = await asyncio.gather(
            *[self.queries.query_rest(f"/repos/{repo}/traffic/views") for repo in repos],
            return_exceptions=True,
        )

        total = 0
        for r in results:
            if not isinstance(r, dict):
                continue
            for view in r.get("views", []):
                if isinstance(view, dict):
                    total += view.get("count", 0)

        self._views = total
        return total

    @property
    async def prs_opened(self) -> int:
        """
        :return: total number of pull requests the user has opened (all time)
        """
        if self._prs_opened is not None:
            return self._prs_opened
        r = await self.queries.query_rest(
            "/search/issues",
            params={"q": f"is:pr author:{self.username}", "per_page": 1},
        )
        self._prs_opened = int(r.get("total_count", 0)) if isinstance(r, dict) else 0
        return self._prs_opened

    @property
    async def prs_merged(self) -> int:
        """
        :return: total number of the user's pull requests that were merged
        """
        if self._prs_merged is not None:
            return self._prs_merged
        r = await self.queries.query_rest(
            "/search/issues",
            params={"q": f"is:pr author:{self.username} is:merged", "per_page": 1},
        )
        self._prs_merged = int(r.get("total_count", 0)) if isinstance(r, dict) else 0
        return self._prs_merged

    async def _contributions(self) -> Dict[str, int]:
        """
        Viewer-scoped contribution counts for the trailing year via GraphQL.
        Unlike the Search API these include private repositories, because they
        are scoped to the authenticated viewer rather than to token-granted
        repositories. Cached across properties.
        """
        if self._contrib is None:
            r = await self.queries.query(
                """{
  viewer {
    contributionsCollection {
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalCommitContributions
      totalRepositoryContributions
    }
  }
}"""
            )
            self._contrib = r.get("data", {}).get("viewer", {}).get("contributionsCollection", {}) or {}
        return self._contrib

    @property
    async def pr_contributions(self) -> int:
        if self._contrib is None:
            await self._contributions()
        return int(self._contrib.get("totalPullRequestContributions", 0))

    @property
    async def commit_contributions(self) -> int:
        if self._contrib is None:
            await self._contributions()
        return int(self._contrib.get("totalCommitContributions", 0))

    @property
    async def repository_contributions(self) -> int:
        if self._contrib is None:
            await self._contributions()
        return int(self._contrib.get("totalRepositoryContributions", 0))

    async def preflight(self) -> str:
        """
        Verify that the access token is valid before generating any images, so
        that an expired token cannot silently overwrite good images with zeros.
        :return: the authenticated viewer's login
        :raises RuntimeError: when the token is missing, expired, or mis-scoped
        """
        result = await self.queries.query(Queries.viewer_login())
        if result.get("errors"):
            raise RuntimeError(
                "GitHub API rejected the token: "
                + str(result["errors"][0].get("message", "unknown error"))
            )
        login = result.get("data", {}).get("viewer", {}).get("login")
        if not login:
            raise RuntimeError(
                "GitHub API returned no authenticated viewer. ACCESS_TOKEN is "
                "missing, expired, or lacks the required read:user/repo scopes."
            )
        return login

    @property
    async def contributions_calendar(self) -> List[List[Dict[str, Any]]]:
        """
        Daily contribution calendar for roughly the trailing year, grouped into
        weeks (Sunday -> Saturday). Powers the streak and contribution-graph
        cards. Returns an empty list when the API has no data for the range.
        :return: list of weeks, each a list of {date, contributionCount} days
        """
        if self._calendar is not None:
            return self._calendar

        today = datetime.now(timezone.utc)
        from_date = (today - timedelta(days=370)).strftime("%Y-%m-%dT00:00:00Z")
        to_date = today.strftime("%Y-%m-%dT23:59:59Z")

        result = await self.queries.query(
            Queries.contributions_calendar(from_date, to_date)
        )
        weeks = (
            result.get("data", {})
            .get("viewer", {})
            .get("contributionsCollection", {})
            .get("contributionCalendar", {})
            .get("weeks", [])
        )
        # GraphQL returns each week as an object wrapping its day list; flatten
        # to a list of day dicts so consumers can iterate weeks -> days directly.
        weeks = [w.get("contributionDays", []) for w in weeks]
        self._calendar = weeks
        return weeks


###############################################################################
# Main Function
###############################################################################


async def main() -> None:
    """
    Used mostly for testing; this module is not usually run standalone
    """
    access_token = os.getenv("ACCESS_TOKEN")
    user = os.getenv("GITHUB_ACTOR")
    if access_token is None or user is None:
        raise RuntimeError(
            "ACCESS_TOKEN and GITHUB_ACTOR environment variables cannot be None!"
        )
    async with aiohttp.ClientSession() as session:
        s = Stats(user, access_token, session)
        print(await s.to_str())


if __name__ == "__main__":
    asyncio.run(main())
