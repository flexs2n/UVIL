use vstd::prelude::*;

fn main() {}

verus! {

fn gen_add_comm(x: i32, y: i32)
    requires x >= 0, y >= 0,
    ensures x + y == y + x,
{
}

}
