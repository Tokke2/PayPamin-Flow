import unittest

import cv2
import numpy as np

import donations
import qr_code


def render(matrix, quiet=4, scale=6):
    """Draw a matrix as a white image with black modules, like the app does."""
    size = len(matrix)
    total = (size + 2 * quiet) * scale
    image = np.full((total, total), 255, dtype=np.uint8)
    for row_index, row in enumerate(matrix):
        for column_index, dark in enumerate(row):
            if dark:
                top = (row_index + quiet) * scale
                left = (column_index + quiet) * scale
                image[top:top + scale, left:left + scale] = 0
    return image


class QrStructureTests(unittest.TestCase):
    def test_a_short_payload_uses_the_smallest_version_that_fits(self):
        self.assertEqual(len(qr_code.encode("A")), 21)
        self.assertEqual(len(qr_code.encode("C0721817177;50;;6")), 25)
        self.assertEqual(len(qr_code.encode("x" * 40)), 29)
        self.assertEqual(len(qr_code.encode("y" * 60)), 33)

    def test_the_grid_is_square_and_only_holds_booleans(self):
        matrix = qr_code.encode("C0721817177;50;;6")
        self.assertTrue(all(len(row) == len(matrix) for row in matrix))
        self.assertTrue(all(isinstance(value, bool) for row in matrix for value in row))

    def test_the_three_finder_patterns_are_where_the_spec_says(self):
        matrix = qr_code.encode("C0721817177;50;;6")
        size = len(matrix)
        for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
            for row in range(7):
                for column in range(7):
                    border = row in (0, 6) or column in (0, 6)
                    core = 2 <= row <= 4 and 2 <= column <= 4
                    self.assertEqual(
                        matrix[top + row][left + column],
                        border or core,
                        f"finder at {top},{left} module {row},{column}",
                    )

    def test_every_mask_is_accepted_and_a_bad_one_is_refused(self):
        for mask in range(8):
            self.assertEqual(len(qr_code.encode("test", mask=mask)), 21)
        for mask in (-1, 8, "x"):
            with self.assertRaises(ValueError):
                qr_code.encode("test", mask=mask)

    def test_too_much_data_is_refused_instead_of_truncated(self):
        with self.assertRaises(ValueError):
            qr_code.encode("x" * 63)
        with self.assertRaises(ValueError):
            qr_code.encode("")

    def test_the_chosen_mask_has_the_lowest_penalty(self):
        payload = "C0721817177;50;;6"
        chosen = qr_code.encode(payload)
        scores = [qr_code.penalty_score(qr_code.encode(payload, mask=mask)) for mask in range(8)]
        self.assertEqual(qr_code.penalty_score(chosen), min(scores))

    def test_text_and_bytes_give_the_same_code(self):
        self.assertEqual(qr_code.encode("C0721817177;50;;6"), qr_code.encode(b"C0721817177;50;;6"))


class QrDecodeTests(unittest.TestCase):
    """A scanner must read exactly the Swish payload back out of the grid."""

    def decode(self, matrix):
        detector = cv2.QRCodeDetector()
        text, _points, _straight = detector.detectAndDecode(render(matrix))
        return text

    def test_every_fixed_amount_decodes_to_the_swish_payload(self):
        for amount in donations.AMOUNTS:
            payload = donations.swish_payload(amount)
            with self.subTest(amount=amount):
                self.assertEqual(self.decode(qr_code.encode(payload)), payload)

    def test_every_mask_of_the_real_payload_still_scans(self):
        payload = donations.swish_payload()
        for mask in range(8):
            with self.subTest(mask=mask):
                self.assertEqual(self.decode(qr_code.encode(payload, mask=mask)), payload)

    def test_the_number_in_the_code_is_the_locked_number(self):
        payload = donations.swish_payload(100)
        self.assertTrue(payload.startswith("C0721817177;100;"))
        self.assertEqual(self.decode(qr_code.encode(payload)), "C0721817177;100;;6")


if __name__ == "__main__":
    unittest.main()
