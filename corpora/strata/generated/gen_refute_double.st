program Core;

procedure refute_double(x : int)
spec {
}
{
  assert [c]: (int.add(x, x) == int.mul(3, x));
};
