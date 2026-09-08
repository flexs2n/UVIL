procedure p_fermat_2(x: int, y: int, z: int)
  requires x >= 3 && y >= 3 && z >= 3
{
  assert x * x * x * x * x + y * y * y * y * y != z * z * z * z * z;
}
