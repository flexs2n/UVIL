use vstd::prelude::*;

fn main() {}

verus! {

fn gen_refute_bound(x: i32, y: i32)
    requires x >= 0,
    ensures x - y == 10,
{
}

}
