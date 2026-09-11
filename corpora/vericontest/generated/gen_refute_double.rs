use vstd::prelude::*;

fn main() {}

verus! {

fn gen_refute_double(x: i32)
    requires x == 5,
    ensures x * 2 == 12,
{
}

}
