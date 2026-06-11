from pydantic import BaseModel, Field
from typing import Union

class SLAExtractionPayload(BaseModel):
    kode: str = Field(..., description="The unique Kode found on the watermark or caption. This is the anchor code.")
    tanggal_perbaikan: str = Field(..., description="Date of repair found on the watermark")
    metode_perbaikan: str = Field(default="", description="Method of repair found on the watermark, if any")
    sheet_name: str = Field(..., description="The exact sheet name to update. You must infer this. E.g. 'PV' for pavement, 'GD' for guardrail, 'MJ' for marking, etc.")
    panjang: Union[str, float, int] = Field(default="", description="Panjang (Length) of repair, if provided in caption")
    lebar: Union[str, float, int] = Field(default="", description="Lebar (Width) of repair, if provided in caption")
    tebal: Union[str, float, int] = Field(default="", description="Tebal (Thickness) of repair, if provided in caption")
