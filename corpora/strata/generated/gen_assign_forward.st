program Core;

procedure assign_forward(x : int)
spec {
}
{
  var y : int;
  y := int.add(x, 1);
  assert [c]: (int.ge(y, int.add(x, 1)));
};
