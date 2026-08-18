import pytest

from src.meta import Meta
from src.region import get_distributor, get_region
from src.trackers.common import Common
from src.trackers.UNIT3D.aither import Aither
from src.trackers.UNIT3D.blutopia import Blutopia
from src.trackers.UNIT3D.lst import LST


@pytest.mark.asyncio
async def test_get_region_from_json():
    # USA in label
    bdinfo = {"label": "Movie 2024 USA 1080p Bluray"}
    region = await get_region(bdinfo)
    assert region == "USA"

    # Explicit region override
    region = await get_region(bdinfo, region="gbr")
    assert region == "GBR"

    # None if not matched
    bdinfo_empty = {"label": "Movie 2024 1080p Bluray"}
    region = await get_region(bdinfo_empty)
    assert region == ""


@pytest.mark.asyncio
async def test_get_distributor_from_json():
    dist = await get_distributor("01 DISTRIBUTION")
    assert dist == "01 DISTRIBUTION"

    dist = await get_distributor("20th century fox")
    assert dist == "20TH CENTURY FOX"

    dist = await get_distributor(None)
    assert dist == ""


@pytest.mark.asyncio
async def test_common_unit3d_ids_from_json():
    common = Common({})

    # Forward region
    region_id = await common.unit3d_region_ids("USA")
    assert region_id == "229"

    # Reverse region
    region_code = await common.unit3d_region_ids(reverse=True, region_id=229)
    assert region_code == "USA"

    # Forward distributor
    dist_id = await common.unit3d_distributor_ids("01 DISTRIBUTION")
    assert dist_id == "1"

    # Reverse distributor
    dist_name = await common.unit3d_distributor_ids(reverse=True, distributor_id=1)
    assert dist_name == "01 DISTRIBUTION"


@pytest.mark.asyncio
async def test_tracker_specific_json_overrides():
    config = {"TRACKERS": {"AITHER": {}, "BLUTOPIA": {}, "LST": {}}}

    aither = Aither(config)
    blutopia = Blutopia(config)
    lst = LST(config)

    # 1. Custom Tracker-specific Forward mapping
    # FIN: Aither=244, Blutopia=246, LST=245
    meta_fin = Meta(region="FIN")
    assert (await aither.get_region_id(meta_fin)) == {"region_id": "244"}
    assert (await blutopia.get_region_id(meta_fin)) == {"region_id": "246"}
    assert (await lst.get_region_id(meta_fin)) == {"region_id": "245"}

    # CZE: Aither=247, Blutopia=244, LST=244
    meta_cze = Meta(region="CZE")
    assert (await aither.get_region_id(meta_cze)) == {"region_id": "247"}
    assert (await blutopia.get_region_id(meta_cze)) == {"region_id": "244"}
    assert (await lst.get_region_id(meta_cze)) == {"region_id": "244"}

    # 2. Custom Tracker-specific Reverse mapping
    assert (await aither.get_region_name("244")) == "FIN"
    assert (await blutopia.get_region_name("244")) == "CZE"
    assert (await lst.get_region_name("244")) == "CZE"

    # 3. Fallback to standard global region (USA -> 229)
    meta_usa = Meta(region="USA")
    assert (await aither.get_region_id(meta_usa)) == {"region_id": "229"}
    assert (await aither.get_region_name("229")) == "USA"
