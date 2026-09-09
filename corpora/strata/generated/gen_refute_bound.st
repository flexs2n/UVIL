program Core;

procedure refute_bound(x : int)
spec {
  requires (int.ge(x, 10));
}
{
  assert [c]: (int.le(x, 5));
};
