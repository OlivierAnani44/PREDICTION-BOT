#!/usr/bin/env python3
"""
ESPN Football Data Collector
Fetches real match data, team info, and statistics from ESPN's API.
"""

import aiohttp
import asyncio
import json
from datetime import datetime

class ESPNDataCollector:
    """
    Collects real football data from ESPN's public API.
    Structure: https://site.api.espn.com/apis/site/v2/sports/soccer/{LEAGUE_CODE}/{ENDPOINT}
    """

    def __init__(self):
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports/soccer"
        # Common league codes [citation:5][citation:6]
        self.leagues = {
            'premier_league': 'eng.1',
            'la_liga': 'esp.1',
            'bundesliga': 'ger.1',
            'serie_a': 'ita.1',
            'ligue_1': 'fra.1',
            'champions_league': 'uefa.champions',
            'europa_league': 'uefa.europa'
        }

    async def fetch(self, session, url, params=None):
        """Generic method to fetch data from an API endpoint."""
        try:
            async with session.get(url, params=params, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"HTTP Error {response.status} for {url}")
                    return None
        except Exception as e:
            print(f"Request failed for {url}: {e}")
            return None

    async def get_todays_matches(self, league_key='premier_league'):
        """
        Fetches today's matches for a given league.
        Returns: List of match objects with IDs, teams, date, and status.
        """
        if league_key not in self.leagues:
            print(f"League {league_key} not found.")
            return []

        league_code = self.leagues[league_key]
        # Format date as YYYYMMDD [citation:6]
        date_str = datetime.now().strftime("%Y%m%d")
        url = f"{self.base_url}/{league_code}/scoreboard"
        params = {"dates": date_str}

        async with aiohttp.ClientSession() as session:
            data = await self.fetch(session, url, params)
            if not data or 'events' not in data:
                print(f"No match data found for {league_key} on {date_str}.")
                return []

            matches = []
            for event in data['events']:
                match_info = {
                    'match_id': event.get('id'),
                    'date': event.get('date'),
                    'name': event.get('name'),
                    'short_name': event.get('shortName'),
                    'status': event.get('status', {}).get('type', {}).get('description', 'Scheduled')
                }
                # Extract team info
                competitions = event.get('competitions', [])
                if competitions:
                    competitors = competitions[0].get('competitors', [])
                    for competitor in competitors:
                        if competitor.get('homeAway') == 'home':
                            match_info['home_team'] = competitor.get('team', {}).get('displayName')
                            match_info['home_id'] = competitor.get('team', {}).get('id')
                        else:
                            match_info['away_team'] = competitor.get('team', {}).get('displayName')
                            match_info['away_id'] = competitor.get('team', {}).get('id')
                matches.append(match_info)

            print(f"Found {len(matches)} matches for {league_key}.")
            return matches

    async def get_team_details(self, team_id, league_key='premier_league'):
        """
        Fetches detailed information for a specific team.
        Includes roster, team stats, and record [citation:6][citation:7].
        """
        if league_key not in self.leagues:
            return None

        league_code = self.leagues[league_key]
        # Use the 'enable' parameter to get rosters [citation:7]
        url = f"{self.base_url}/{league_code}/teams/{team_id}"
        params = {"enable": "roster"}

        async with aiohttp.ClientSession() as session:
            data = await self.fetch(session, url, params)
            if not data:
                return None

            team_info = {
                'id': data.get('team', {}).get('id'),
                'name': data.get('team', {}).get('displayName'),
                'abbreviation': data.get('team', {}).get('abbreviation'),
                'record': data.get('team', {}).get('record', {}),
                'athletes': []
            }

            # Extract player roster if available
            for group in data.get('athletes', []):
                for athlete in group.get('items', []):
                    player = {
                        'id': athlete.get('id'),
                        'full_name': athlete.get('fullName'),
                        'position': athlete.get('position', {}).get('abbreviation'),
                        'jersey': athlete.get('jersey')
                    }
                    team_info['athletes'].append(player)

            return team_info

    async def get_match_summary(self, event_id, league_key='premier_league'):
        """
        Fetches detailed summary for a specific match (play-by-play, box score, stats).
        This is where you get REAL, DETAILED statistics [citation:2].
        """
        if league_key not in self.leagues:
            return None

        league_code = self.leagues[league_key]
        # The summary endpoint contains comprehensive data [citation:2]
        url = f"{self.base_url}/{league_code}/summary"
        params = {"event": event_id}

        async with aiohttp.ClientSession() as session:
            data = await self.fetch(session, url, params)
            if not data:
                return None

            # The structure here is rich. This extracts key parts.
            summary = {
                'boxscore': data.get('boxscore', {}),
                'game_info': data.get('gameInfo', {}),
                'headlines': data.get('headlines', []),
                'winprobability': data.get('winprobability', []),
                'leaders': data.get('leaders', []),
                # 'plays' contains the detailed play-by-play events
                'plays': data.get('plays', [])
            }

            # Example: Extract team statistics from the boxscore
            teams_stats = []
            for team in summary['boxscore'].get('teams', []):
                team_data = {
                    'team_name': team.get('team', {}).get('displayName'),
                    'statistics': []
                }
                for stat in team.get('statistics', []):
                    team_data['statistics'].append({
                        'name': stat.get('name'),
                        'displayValue': stat.get('displayValue'),
                        'label': stat.get('label')
                    })
                teams_stats.append(team_data)
            summary['team_statistics'] = teams_stats

            return summary

async def main():
    """Example of how to use the collector."""
    collector = ESPNDataCollector()

    print("=== ESPN REAL DATA COLLECTOR ===\n")

    # 1. Get today's Premier League matches
    print("1. Fetching today's Premier League matches...")
    matches = await collector.get_todays_matches('premier_league')
    for match in matches[:2]:  # Show first two
        print(f"   - {match['home_team']} vs {match['away_team']} (ID: {match['match_id']})")

    if matches:
        first_match_id = matches[0]['match_id']
        first_home_id = matches[0].get('home_id')

        # 2. Get details of the first match
        print(f"\n2. Fetching detailed summary for match ID {first_match_id}...")
        match_summary = await collector.get_match_summary(first_match_id, 'premier_league')
        if match_summary and 'team_statistics' in match_summary:
            print("   Real match statistics found (e.g., possession, shots, passes).")
            # You can save this JSON for analysis: json.dump(match_summary, open('match_data.json', 'w'), indent=2)

        # 3. Get details of the first team
        if first_home_id:
            print(f"\n3. Fetching details for team ID {first_home_id}...")
            team_details = await collector.get_team_details(first_home_id, 'premier_league')
            if team_details:
                print(f"   Team: {team_details['name']} ({team_details['abbreviation']})")
                print(f"   Has {len(team_details['athletes'])} players in roster.")

    print("\n=== Data collection complete. ===")
    print("You can now analyze the JSON data structures returned by these functions.")

if __name__ == "__main__":
    asyncio.run(main())