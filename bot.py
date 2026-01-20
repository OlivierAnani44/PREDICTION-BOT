#!/usr/bin/env python3
"""
Multi-League ESPN Data Collector Test
Tests the user's list of leagues for available match data.
"""
import aiohttp
import asyncio
from datetime import datetime

class MultiLeagueCollector:
    def __init__(self):
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports/soccer"
        # ESPN league code mapping
        self.league_mapping = {
            "Algérie - Ligue 1": "dza.1",
            "Allemagne - Bundesliga": "ger.1",
            "Allemagne - Bundesliga 2": "ger.2",
            "Allemagne - Coupe d'Allemagne": "ger.cup",
            "Angleterre - Premier League": "eng.1",
            "Angleterre - Championship": "eng.2",
            "Angleterre - FA Cup": "eng.fa",
            "Angleterre - League Cup": "eng.league_cup",
            "Arabie Saoudite - Saudi Pro League": "ksa.1",
            "Autriche - Bundesliga": "aut.1",
            "Belgique - Jupiler Pro League": "bel.1",
            "Brésil - Serie A": "bra.1",
            "Cameroun - Elite One": "cmr.1",
            "Côte d'Ivoire - Ligue 1": "civ.1",
            "Écosse - Premiership": "sco.1",
            "Égypte - Premier League": "egy.1",
            "Espagne - Liga": "esp.1",
            "Espagne - Segunda Division": "esp.2",
            "Espagne - Copa del Rey": "esp.cup",
            "Etats-Unis - Major League Soccer": "usa.1",
            "Europe - Ligue des champions": "uefa.champions",
            "Europe - Ligue Europa": "uefa.europa",
            "Europe - Europa Conference League": "uefa.europa_conference",
            "France - Ligue 1": "fra.1",
            "France - Ligue 2": "fra.2",
            "France - Coupe de France": "fra.cup",
            "Grèce - Super League": "gre.1",
            "Italie - Serie A": "ita.1",
            "Italie - Serie B": "ita.2",
            "Italie - Coupe d'Italie": "ita.cup",
            "Maroc - GNEF 1": "mar.1",
            "Mexique - Liga MX": "mex.1",
            "Norvège - Eliteserien": "nor.1",
            "Pays-Bas - Eredivisie": "ned.1",
            "Portugal - Liga": "por.1",
            "Portugal - Segunda Liga": "por.2",
            "Portugal - Coupe du Portugal": "por.cup",
            "Russie - Premier League": "rus.1",
            "Sénégal - Ligue 1": "sen.1",
            "Suisse - Super League": "sui.1",
            "Tunisie - Ligue 1": "tun.1",
            "Turquie - Süper Lig": "tur.1",
            "Ukraine - Premier League": "ukr.1",
        }
    
    async def test_league(self, session, league_name, league_code, test_date):
        """Test if a specific league has data for a given date."""
        url = f"{self.base_url}/{league_code}/scoreboard"
        params = {"dates": test_date}
        try:
            async with session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    events = data.get('events', [])
                    return len(events)
                return 0
        except:
            return -1  # Error indicator

    async def run_test(self):
        """Run the multi-league test and print results."""
        # Test date: October 19, 2024 (a historical Saturday with many matches)
        historical_date = "20241019"
        # Use your computer's current date for comparison
        current_date = datetime.now().strftime("%Y%m%d")
        
        print(f"🔍 Testing {len(self.league_mapping)} leagues...")
        print(f"   Historical Date: {historical_date}")
        print(f"   Current Date: {current_date}")
        print("-" * 70)
        
        results = []
        async with aiohttp.ClientSession() as session:
            for league_display, league_code in self.league_mapping.items():
                # Test historical date first
                hist_matches = await self.test_league(session, league_display, league_code, historical_date)
                
                # Only test current date if historical date has data
                curr_matches = 0
                if hist_matches > 0:
                    curr_matches = await self.test_league(session, league_display, league_code, current_date)
                
                results.append({
                    'League': league_display,
                    'ESPN Code': league_code,
                    f'Matches on {historical_date}': hist_matches,
                    f'Matches on {current_date}': curr_matches
                })
        
        # Print results table
        print("\n📋 TEST RESULTS:")
        print(f"{'League':<40} | {'ESPN Code':<20} | Hist Date | Curr Date")
        print("-" * 85)
        
        for res in results:
            hist_count = res[f'Matches on {historical_date}']
            curr_count = res[f'Matches on {current_date}']
            
            hist_display = f"{hist_count:>9}" if hist_count >= 0 else "    Error"
            curr_display = f"{curr_count:>9}" if curr_count >= 0 else "    Error"
            
            print(f"{res['League'][:38]:<40} | {res['ESPN Code']:<20} | {hist_display} | {curr_display}")
        
        # Summary statistics
        leagues_with_hist_data = sum(1 for r in results if r[f'Matches on {historical_date}'] > 0)
        leagues_with_curr_data = sum(1 for r in results if r[f'Matches on {current_date}'] > 0)
        
        print("\n📊 SUMMARY:")
        print(f"• {leagues_with_hist_data}/{len(results)} leagues have historical data on {historical_date}")
        print(f"• {leagues_with_curr_data}/{leagues_with_hist_data} of those have current data today")
        
        # Recommendations
        print("\n🎯 RECOMMENDED LEAGUES TO FETCH DATA FROM:")
        for res in results:
            if res[f'Matches on {historical_date}'] > 3:  # Leagues with decent data
                print(f"  • {res['League']} (Code: {res['ESPN Code']}) - {res[f'Matches on {historical_date}']} matches")

async def main():
    collector = MultiLeagueCollector()
    await collector.run_test()

if __name__ == "__main__":
    asyncio.run(main())