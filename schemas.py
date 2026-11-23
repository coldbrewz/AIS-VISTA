from pydantic import BaseModel, Field
from typing import List, Optional, Union

class SLAExtractionPayload(BaseModel):
    kode: str = Field(..., description="The unique Kode found on the watermark or caption. This is the anchor code.")
    tanggal_perbaikan: str = Field(..., description="Date of repair found on the watermark")
    metode_perbaikan: str = Field(default="", description="Method of repair found on the watermark, if any")
    sheet_name: str = Field(..., description="The exact sheet name to update. You must infer this. E.g. 'PV' for pavement, 'GD' for guardrail, 'MJ' for marking, etc.")
    panjang: Union[str, float, int] = Field(default="", description="Panjang (Length) of repair, if provided in caption")
    lebar: Union[str, float, int] = Field(default="", description="Lebar (Width) of repair, if provided in caption")
    tebal: Union[str, float, int] = Field(default="", description="Tebal (Thickness) of repair, if provided in caption")


class OpnameLineItem(BaseModel):
    item_key: str = Field(..., description="Canonical BOQ Item_Key matching DATA UNTUK VOL")
    uraian_boq: str = Field(..., description="Official BOQ description")
    p: Optional[float] = None
    l: Optional[float] = None
    t: Optional[float] = None
    jumlah: Optional[float] = None
    volume: float = Field(..., gt=0, description="Calculated or explicit item volume > 0")
    satuan: str = Field(default="", description="Measurement unit")
    material_status: str = Field(default="", description="Baru or Eksisting when applicable")


class OpnameExtractionPayload(BaseModel):
    aset: str = Field(..., description="Canonical 2-letter asset code e.g., PV, GR, SG, WR, RM, LC, CA, DR, FE")
    kode_temuan: str = Field(default="", description="Optional SLA finding code or '-' if routine")
    tanggal: str = Field(..., description="Work date in YYYY-MM-DD format")
    lokasi: str = Field(..., description="KM/STA or IC/Akses location")
    wilayah: str = Field(..., description="Resolved Wilayah: W1 or W2")
    jalur_lajur: str = Field(default="", description="Lane / direction e.g., A L1, B, Median, ROW")
    vendor: str = Field(..., description="Normalized canonical vendor name")
    items: List[OpnameLineItem] = Field(..., min_length=1)
    keterangan: str = Field(default="", description="Optional free text note")
