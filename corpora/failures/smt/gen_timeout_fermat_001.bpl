procedure p_fermat_1(x: int, y: int, z: int)
  requires x >= 2 && y >= 2 && z >= 2
{
  assert x * x * x * x * x + y * y * y * y * y != z * z * z * z * z;
}
