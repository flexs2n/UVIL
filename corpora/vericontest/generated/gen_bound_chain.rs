use vstd::prelude::*;

fn main() {}

verus! {

fn gen_bound_chain(x: i32, y: i32)
    requires x >= 0, y >= x,
    ensures y >= x,
{
}

}
