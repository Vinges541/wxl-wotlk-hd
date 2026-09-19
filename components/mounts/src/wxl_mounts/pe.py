"""Read-only PE32 structure inspector, derived from WarcraftXL/races (GPL-3.0+)."""
import struct
from dataclasses import dataclass
class PatchError(RuntimeError):
  pass

@dataclass(frozen=True)
class Section:
  header_offset: int
  name: str
  virtual_size: int
  virtual_address: int
  raw_size: int
  raw_offset: int

class Pe32:
  def __init__(self, data: bytearray) -> None:
    self.data = data
    if len(data) < 0x40 or data[:2] != b"MZ":
      raise PatchError("not an MZ executable")
    self.nt = self.u32(0x3C)
    if self.nt + 24 > len(data) or data[self.nt:self.nt + 4] != b"PE\0\0":
      raise PatchError("not a PE executable")
    self.file_header = self.nt + 4
    self.optional = self.nt + 24
    if self.u16(self.optional) != 0x10B:
      raise PatchError("WarcraftXL requires a 32-bit PE executable")
    self.optional_size = self.u16(self.file_header + 16)
    if self.optional + self.optional_size > len(data):
      raise PatchError("truncated PE optional header")
    self.section_table = self.optional + self.optional_size
    self._validate_sections()

  def u16(self, offset: int) -> int:
    return struct.unpack_from("<H", self.data, offset)[0]

  def u32(self, offset: int) -> int:
    return struct.unpack_from("<I", self.data, offset)[0]



  @property
  def section_count(self) -> int:
    return self.u16(self.file_header + 2)

  @property
  def image_base(self) -> int:
    return self.u32(self.optional + 28)



  @property
  def size_of_headers(self) -> int:
    return self.u32(self.optional + 60)

  def sections(self) -> list[Section]:
    result = []
    for index in range(self.section_count):
      offset = self.section_table + index * 40
      raw_name = bytes(self.data[offset:offset + 8]).split(b"\0", 1)[0]
      result.append(Section(
        header_offset=offset,
        name=raw_name.decode("ascii", errors="replace"),
        virtual_size=self.u32(offset + 8),
        virtual_address=self.u32(offset + 12),
        raw_size=self.u32(offset + 16),
        raw_offset=self.u32(offset + 20),
      ))
    return result

  def _validate_sections(self) -> None:
    end = self.section_table + self.section_count * 40
    if end > len(self.data) or end > self.size_of_headers:
      raise PatchError("truncated or invalid PE section table")





  def data_directory(self, index: int) -> tuple[int, int]:
    offset = self.optional + 96 + index * 8
    return self.u32(offset), self.u32(offset + 4)
