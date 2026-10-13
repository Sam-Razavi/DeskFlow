import csv
import io

import pytest

from app.services.csv_export import safe_cell, to_csv


@pytest.mark.parametrize(
    "dangerous", ["=1+1", "+1", "-1", "@SUM(A1)", "\tcmd", "\rcmd", '=HYPERLINK("http://evil")']
)
def test_cells_that_a_spreadsheet_would_run_are_neutralised(dangerous):
    assert safe_cell(dangerous) == "'" + dangerous


@pytest.mark.parametrize(
    "harmless", ["Alan Agent", "a=b", "x-ray", "email@example.com", "", "12", "ticket created"]
)
def test_ordinary_cells_are_left_alone(harmless):
    assert safe_cell(harmless) == harmless


def test_none_becomes_an_empty_cell():
    assert safe_cell(None) == ""


def test_to_csv_quotes_commas_quotes_and_newlines_so_it_round_trips():
    tricky = ['He said "hi", then left', "two\nlines", "=cmd", "ünïcödé ✓"]
    text = to_csv(["a", "b", "c", "d"], [tricky])
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == ["a", "b", "c", "d"]
    assert parsed[1] == ['He said "hi", then left', "two\nlines", "'=cmd", "ünïcödé ✓"]
