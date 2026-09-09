program Core;

procedure distrib(x : int, y : int, z : int)
spec {
}
{
  assert [c]: (int.mul(x, int.add(y, z)) == int.add(int.mul(x, y), int.mul(x, z)));
};
