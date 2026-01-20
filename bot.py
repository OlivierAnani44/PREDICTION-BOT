import soccerdata as sd

# 1. Initialize the ESPN reader for the correct league and season
# The API understands '2021' as the 2020-21 season[citation:1]
espn_reader = sd.ESPN(leagues="ENG-Premier League", seasons=2021)

# 2. Fetch detailed team statistics for match 541465
matchsheet_df = espn_reader.read_matchsheet(match_id=541465)
print("Match Statistics for West Ham vs Aston Villa:")
print(matchsheet_df[['team', 'possession_pct', 'total_shots', 'shots_on_target', 'fouls_committed', 'won_corners']])

# 3. Fetch player lineup and event data
lineup_df = espn_reader.read_lineup(match_id=541465)
print("\nSample Player Data:")
if not lineup_df.empty:
    print(lineup_df[['player', 'position', 'total_goals', 'goal_assists', 'yellow_cards']].head())