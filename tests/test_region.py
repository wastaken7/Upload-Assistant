import json
from pathlib import Path

import pytest

from src.region import get_region


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['label', 'title', 'path'])
@pytest.mark.parametrize('code', ['ALB', 'BGR', 'CZE', 'DNK', 'EST', 'FIN', 'LTU', 'LVA', 'RPA', 'SGP', 'SVK', 'SWE', 'TWN'])
async def test_disc_label_sets_region(field, code):
    assert await get_region({field: f'Example.Movie.{code}.BluRay'}) == code


@pytest.mark.asyncio
async def test_disc_label_preserves_explicit_region():
    assert await get_region({'label': 'Example.Movie.FIN.BluRay'}, 'USA') == 'USA'


@pytest.mark.asyncio
async def test_disc_labels_recognize_all_catalog_regions():
    catalog_dir = Path(__file__).resolve().parents[1] / 'data' / 'unit3d_catalogs'
    codes = set()
    for path in catalog_dir.glob('*.json'):
        codes.update(json.loads(path.read_text(encoding='utf-8')).get('regions', {}).values())

    for code in codes:
        assert await get_region({'label': f'Example.Movie.{code}.BluRay'}) == code
