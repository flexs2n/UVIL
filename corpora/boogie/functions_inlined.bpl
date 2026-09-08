// defined functions are inlined at lowering time
function double(x: int) returns (int) {
  x + x
}

function abs_diff(a: int, b: int) returns (int) {
  if a >= b then a - b else b - a
}

procedure use_double(y: int)
  requires y >= 0
{
  assert double(y) == 2 * y;
}

procedure use_abs_diff(a: int, b: int)
{
  assert abs_diff(a, b) == abs_diff(b, a);
}
