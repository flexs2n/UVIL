program Core;

procedure add_comm(x : int, y : int)
spec {
}
{
  assert [c]: (int.add(x, y) == int.add(y, x));
};
