# UBB Timetable to iCalendar (.ics)

This project converts a UBB timetable HTML table into an iCalendar `.ics` file you can import into any calendar client.

## Requirements

- **Python 3.9+** (uses `zoneinfo`)
- `curl` available in PATH

## Usage

0. Run `python ubb2ics_cli.py` and follow prompts:
1. Enter the URL of your timetable (from https://www.cs.ubbcluj.ro/files/orar/2025-2/tabelar/) (or whatever the current year-sem is!)
2. Enter the start and end dates of the semester (from https://www.cs.ubbcluj.ro/invatamant/structura-anului-universitar/)
3. Enter the start and end dates of any vacation periods (from the year structure)
4. Select which subjects to keep
5. Generate the ics file and import it into your calendar client

## Files

- `ubb2ics_core.py`  
  Logic: fetch HTML, parse table, compute teaching weeks, generate `.ics`
- `ubb2ics_cli.py`  
  Interactive CLI wrapper for configuring everything and writing the `.ics`
