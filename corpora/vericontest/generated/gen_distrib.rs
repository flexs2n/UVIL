use vstd::prelude::*;

fn main() {}

verus! {

fn gen_distrib(x: i32)
    requires x >= 0, x <= 1000,
    ensures x * 2 == x + x,
{
}

}
