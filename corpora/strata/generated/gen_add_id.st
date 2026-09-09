program Core;

procedure add_id(x : int)
spec {
}
{
  assert [c]: (int.add(x, 0) == x);
};
