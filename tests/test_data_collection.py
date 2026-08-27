import csv
import tempfile
import unittest
from pathlib import Path

from ml.src.data import append_records, parse_result_page


CARD_HTML = """
<div class="listingBox" data-id="98765">
  <h2 class="listingTit"><a href="https://www.mubawab.ma/fr/a/98765/appartement-test">Appartement à vendre</a></h2>
  <span class="priceTag">1 500 000 DH</span>
  <p><i class="icon-location"></i>Maârif, Casablanca</p>
  <div class="adDetails">90 m² 3 Pièces 2 Chambres 1 Salle de bain Parking</div>
</div>
"""


class CollectionTests(unittest.TestCase):
    def test_card_parser_preserves_identity_and_raw_fields(self):
        records = parse_result_page(CARD_HTML, "2026-08-14T00:00:00+00:00")
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["listing_id"], "mubawab.ma:native:98765")
        self.assertEqual(record["url"], "https://www.mubawab.ma/fr/a/98765/appartement-test")
        self.assertEqual(record["transaction_type"], "SALE")
        self.assertEqual(record["city"], "Casablanca")
        self.assertTrue(record["parking"])

    def test_checkpoint_append_skips_known_id(self):
        record = parse_result_page(CARD_HTML)[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.csv"
            self.assertEqual(append_records(path, [record]), 1)
            self.assertEqual(append_records(path, [record]), 0)
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertNotIn("", rows[0])


if __name__ == "__main__":
    unittest.main()
