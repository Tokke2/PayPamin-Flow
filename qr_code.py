"""A tiny, dependency-free QR encoder for the Swish payment code.

The app must be able to show its donation QR code on a machine that is offline
and has nothing but the standard library, so the encoder is implemented here
rather than pulled in as another package. It is deliberately small: **byte
mode, error-correction level M, versions 1–4**, which covers the short Swish
payload (``C<number>;<amount>;;6``) with room to spare.

The output is a list of rows of booleans - ``True`` is a dark module - so the
caller decides how to draw it. :func:`penalty_score` and :func:`best_mask` use
the four penalty rules from the specification, which keeps the code easy to
scan even at small sizes.

Everything here is pure functions over plain data: no I/O, no globals and no
Tk, so it is fully testable without a display.
"""
from __future__ import annotations

# Error-correction level M: (total data codewords, EC codewords per block, blocks)
_CAPACITY_M = {
    1: (16, 10, 1),
    2: (28, 16, 1),
    3: (44, 26, 1),
    4: (64, 18, 2),
}
# Byte-mode payload capacity: mode (4 bits) and the character count (8 bits)
# come out of the data codewords, so a version holds slightly fewer bytes than
# it has codewords. Rounding up here would silently drop data.
MAX_DATA_BYTES_M = {
    version: (data * 8 - 12) // 8 for version, (data, _, _) in _CAPACITY_M.items()
}
EC_LEVEL_M_BITS = 0b00

# GF(256) with the QR primitive polynomial x^8 + x^4 + x^3 + x^2 + 1 (0x11D).
_GF_EXP = [0] * 512
_GF_LOG = [0] * 256
_value = 1
for _index in range(255):
    _GF_EXP[_index] = _value
    _GF_LOG[_value] = _index
    _value <<= 1
    if _value & 0x100:
        _value ^= 0x11D
for _index in range(255, 512):
    _GF_EXP[_index] = _GF_EXP[_index - 255]


def _gf_multiply(left: int, right: int) -> int:
    if left == 0 or right == 0:
        return 0
    return _GF_EXP[_GF_LOG[left] + _GF_LOG[right]]


def _rs_generator(degree: int) -> list[int]:
    """Return the Reed–Solomon generator polynomial of the given degree."""
    polynomial = [1]
    for power in range(degree):
        factor = [1, _GF_EXP[power]]
        product = [0] * (len(polynomial) + 1)
        for i, left in enumerate(polynomial):
            for j, right in enumerate(factor):
                product[i + j] ^= _gf_multiply(left, right)
        polynomial = product
    return polynomial


def _rs_remainder(data: list[int], degree: int) -> list[int]:
    """Return the EC codewords for one block of data codewords."""
    generator = _rs_generator(degree)
    remainder = [0] * degree
    for byte in data:
        factor = byte ^ remainder[0]
        remainder = remainder[1:] + [0]
        for index in range(degree):
            remainder[index] ^= _gf_multiply(generator[index + 1], factor)
    return remainder


def _choose_version(length: int) -> int:
    for version in sorted(MAX_DATA_BYTES_M):
        if length <= MAX_DATA_BYTES_M[version]:
            return version
    raise ValueError(f"The QR payload is too long for this encoder: {length} bytes")


def _bit_buffer(data: bytes, version: int) -> list[int]:
    """Encode byte mode into the final data codewords, padding as the spec says."""
    capacity_bytes = _CAPACITY_M[version][0]
    bits: list[int] = []

    def push(value: int, width: int) -> None:
        for shift in range(width - 1, -1, -1):
            bits.append((value >> shift) & 1)

    push(0b0100, 4)  # byte mode
    push(len(data), 8)  # versions 1-9 use an 8-bit character count
    for byte in data:
        push(byte, 8)
    # Terminator, then pad to a whole codeword.
    push(0, min(4, capacity_bytes * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    codewords = [
        int("".join(str(bit) for bit in bits[start:start + 8]), 2)
        for start in range(0, len(bits), 8)
    ]
    # Alternating pad bytes until the data capacity is full.
    padding = (0xEC, 0x11)
    index = 0
    while len(codewords) < capacity_bytes:
        codewords.append(padding[index % 2])
        index += 1
    return codewords


def _interleave(codewords: list[int], version: int) -> list[int]:
    """Split into blocks, add EC codewords and interleave them in spec order."""
    _, ec_per_block, blocks = _CAPACITY_M[version]
    block_length = len(codewords) // blocks
    data_blocks = [codewords[index * block_length:(index + 1) * block_length] for index in range(blocks)]
    ec_blocks = [_rs_remainder(block, ec_per_block) for block in data_blocks]
    result: list[int] = []
    for index in range(block_length):
        for block in data_blocks:
            result.append(block[index])
    for index in range(ec_per_block):
        for block in ec_blocks:
            result.append(block[index])
    return result


def _size(version: int) -> int:
    return version * 4 + 17


def _alignment_centres(version: int) -> list[int]:
    if version == 1:
        return []
    # The first centre is always 6 and the last is size-7. The spacing is the
    # value published in the standard for versions 2-4.
    last = _size(version) - 7
    spacing = {2: 12, 3: 16, 4: 20}[version]
    centres = [6]
    position = last
    while position > 6:
        centres.insert(1, position)
        position -= spacing
    return sorted(set(centres))


def _place_function_patterns(version: int) -> tuple[list[list[bool]], list[list[bool]]]:
    """Return the module grid and a mask of which modules are reserved."""
    size = _size(version)
    modules = [[False] * size for _ in range(size)]
    reserved = [[False] * size for _ in range(size)]

    def set_module(row: int, column: int, dark: bool) -> None:
        modules[row][column] = dark
        reserved[row][column] = True

    def finder(top: int, left: int) -> None:
        for row in range(-1, 8):
            for column in range(-1, 8):
                r, c = top + row, left + column
                if not (0 <= r < size and 0 <= c < size):
                    continue
                inside = 0 <= row <= 6 and 0 <= column <= 6
                border = row in (0, 6) or column in (0, 6)
                core = 2 <= row <= 4 and 2 <= column <= 4
                set_module(r, c, inside and (border or core))

    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)

    for index in range(8, size - 8):
        dark = index % 2 == 0
        set_module(6, index, dark)
        set_module(index, 6, dark)

    centres = _alignment_centres(version)
    for row in centres:
        for column in centres:
            if (row <= 8 and column <= 8) or (row <= 8 and column >= size - 9) or (row >= size - 9 and column <= 8):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    set_module(row + dr, column + dc, max(abs(dr), abs(dc)) != 1)

    # Reserve the format information areas and the dark module.
    for index in range(9):
        if not reserved[8][index]:
            set_module(8, index, False)
        if not reserved[index][8]:
            set_module(index, 8, False)
    for index in range(8):
        set_module(8, size - 1 - index, False)
        set_module(size - 1 - index, 8, False)
    set_module(size - 8, 8, True)

    if version >= 7:  # pragma: no cover - versions 1-4 are the only ones used
        raise ValueError("Version information is not implemented")
    return modules, reserved


def _place_data(modules: list[list[bool]], reserved: list[list[bool]], codewords: list[int]) -> None:
    size = len(modules)
    bits = [(byte >> shift) & 1 for byte in codewords for shift in range(7, -1, -1)]
    index = 0
    column = size - 1
    upward = True
    while column > 0:
        if column == 6:  # the vertical timing pattern is skipped entirely
            column -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for offset in (0, 1):
                col = column - offset
                if reserved[row][col]:
                    continue
                modules[row][col] = bool(bits[index]) if index < len(bits) else False
                index += 1
        upward = not upward
        column -= 2


def _format_bits(mask: int) -> list[int]:
    """Return the 15 format bits for level M and the given mask."""
    data = (EC_LEVEL_M_BITS << 3) | mask
    remainder = data << 10
    generator = 0b10100110111
    for shift in range(14, 9, -1):
        if remainder & (1 << shift):
            remainder ^= generator << (shift - 10)
    value = ((data << 10) | remainder) ^ 0b101010000010010
    return [(value >> shift) & 1 for shift in range(14, -1, -1)]


def _apply_format(modules: list[list[bool]], mask: int) -> None:
    size = len(modules)
    bits = _format_bits(mask)
    bit = 0
    # Around the top-left finder.
    for column in range(6):
        modules[8][column] = bool(bits[bit]); bit += 1
    modules[8][7] = bool(bits[bit]); bit += 1
    modules[8][8] = bool(bits[bit]); bit += 1
    modules[7][8] = bool(bits[bit]); bit += 1
    for row in range(5, -1, -1):
        modules[row][8] = bool(bits[bit]); bit += 1
    # The second copy.
    bit = 0
    for row in range(size - 1, size - 8, -1):
        modules[row][8] = bool(bits[bit]); bit += 1
    for column in range(size - 8, size):
        modules[8][column] = bool(bits[bit]); bit += 1


_MASKS = (
    lambda row, column: (row + column) % 2 == 0,
    lambda row, column: row % 2 == 0,
    lambda row, column: column % 3 == 0,
    lambda row, column: (row + column) % 3 == 0,
    lambda row, column: (row // 2 + column // 3) % 2 == 0,
    lambda row, column: (row * column) % 2 + (row * column) % 3 == 0,
    lambda row, column: ((row * column) % 2 + (row * column) % 3) % 2 == 0,
    lambda row, column: ((row + column) % 2 + (row * column) % 3) % 2 == 0,
)


def _apply_mask(modules: list[list[bool]], reserved: list[list[bool]], mask: int) -> None:
    rule = _MASKS[mask]
    for row, line in enumerate(modules):
        for column in range(len(line)):
            if not reserved[row][column] and rule(row, column):
                line[column] = not line[column]


def penalty_score(modules: list[list[bool]]) -> int:
    """Score a masked grid with the four rules from the specification."""
    size = len(modules)
    score = 0

    # Rule 1: runs of five or more same-coloured modules.
    for lines in (modules, [list(column) for column in zip(*modules)]):
        for line in lines:
            run = 1
            for index in range(1, size):
                if line[index] == line[index - 1]:
                    run += 1
                else:
                    if run >= 5:
                        score += 3 + (run - 5)
                    run = 1
            if run >= 5:
                score += 3 + (run - 5)

    # Rule 2: every 2x2 block of one colour.
    for row in range(size - 1):
        for column in range(size - 1):
            if modules[row][column] == modules[row][column + 1] == modules[row + 1][column] == modules[row + 1][column + 1]:
                score += 3

    # Rule 3: the finder-like pattern, in both directions.
    first = [True, False, True, True, True, False, True, False, False, False, False]
    second = list(reversed(first))
    for line in list(modules) + [list(column) for column in zip(*modules)]:
        for start in range(size - 10):
            window = list(line[start:start + 11])
            if window == first or window == second:
                score += 40

    # Rule 4: deviation from an even spread of dark modules, in steps of 5 %.
    dark = sum(sum(1 for module in line if module) for line in modules)
    deviation = abs(dark * 100 / (size * size) - 50)
    score += int(deviation // 5) * 10
    return score


def _build(version: int, codewords: list[int], mask: int) -> list[list[bool]]:
    modules, reserved = _place_function_patterns(version)
    _place_data(modules, reserved, _interleave(codewords, version))
    _apply_mask(modules, reserved, mask)
    _apply_format(modules, mask)
    return modules


def encode(data, *, mask: int | None = None) -> list[list[bool]]:
    """Return the QR grid for ``data`` as rows of booleans.

    ``mask`` forces one of the eight masks; without it the mask with the lowest
    penalty score is chosen, which is what a scanner expects from a normal code.
    """
    if isinstance(data, str):
        payload = data.encode("utf-8")
    else:
        payload = bytes(data)
    if not payload:
        raise ValueError("The QR payload is empty")
    version = _choose_version(len(payload))
    codewords = _bit_buffer(payload, version)
    if mask is not None:
        if not 0 <= int(mask) <= 7:
            raise ValueError("A QR mask is 0-7")
        return _build(version, codewords, int(mask))
    candidates = [(_build(version, codewords, value), value) for value in range(8)]
    best = min(candidates, key=lambda item: (penalty_score(item[0]), item[1]))
    return best[0]


def capacity_bytes(version: int) -> int:
    """Return how many payload bytes a version holds at level M."""
    try:
        return MAX_DATA_BYTES_M[int(version)]
    except KeyError:
        raise ValueError("Only versions 1-4 are supported") from None
