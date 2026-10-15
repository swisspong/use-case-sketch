"""Image coverage estimate: union of visible image bounding boxes in the crop box.

Handles inline images, repeated images and nested Form XObjects. Vector drawings
and clipping paths are not images. Rotated image bounds can overestimate coverage.
"""

from itertools import pairwise

from pypdf import mult
from pypdf.generic import ContentStream


def union_area(rectangles):
    xs = sorted({x for r in rectangles for x in (r[0], r[2])})
    area = 0.0
    for left, right in pairwise(xs):
        intervals = sorted(
            (r[1], r[3]) for r in rectangles if r[0] < right and r[2] > left
        )
        end = float("-inf")
        height = 0.0
        for bottom, top in intervals:
            height += max(0, top - max(bottom, end))
            end = max(end, top)
        area += (right - left) * height
    return area


def image_coverage(page, reader):
    box = page.cropbox
    bounds = (float(box.left), float(box.bottom), float(box.right), float(box.top))
    page_area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
    if page_area <= 0:
        raise ValueError("Invalid page dimensions")
    rectangles = []
    identity = [1, 0, 0, 1, 0, 0]

    def image(matrix):
        a, b, c, d, e, f = matrix
        points = [(e, f), (a + e, b + f), (c + e, d + f), (a + c + e, b + d + f)]
        rect = (
            max(bounds[0], min(p[0] for p in points)),
            max(bounds[1], min(p[1] for p in points)),
            min(bounds[2], max(p[0] for p in points)),
            min(bounds[3], max(p[1] for p in points)),
        )
        if rect[2] > rect[0] and rect[3] > rect[1]:
            rectangles.append(rect)

    def walk(stream, resources, matrix, ancestors):
        if stream is None:
            return
        stack = []
        for operands, operator in ContentStream(stream, reader).operations:
            if operator == b"q":
                stack.append(matrix[:])
            elif operator == b"Q":
                matrix = stack.pop()
            elif operator == b"cm":
                matrix = mult([float(v) for v in operands], matrix)
            elif operator == b"INLINE IMAGE":
                image(matrix)
            elif operator == b"Do":
                obj = resources["/XObject"][operands[0]].get_object()
                if obj.get("/Subtype") == "/Image":
                    image(matrix)
                elif obj.get("/Subtype") == "/Form":
                    token = id(obj)
                    if token in ancestors:
                        raise ValueError("Recursive Form XObject")
                    walk(
                        obj,
                        obj.get("/Resources", resources),
                        mult([float(v) for v in obj.get("/Matrix", identity)], matrix),
                        ancestors | {token},
                    )

    walk(page.get_contents(), page.get("/Resources", {}), identity, set())
    return min(100.0, 100 * union_area(rectangles) / page_area)
