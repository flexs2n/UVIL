procedure p_fermat_3(x: int, y: int, z: int)
  requires x >= 4 && y >= 4 && z >= 4
{
  assert x * x * x * x * x + y * y * y * y * y != z * z * z * z * z;
}
