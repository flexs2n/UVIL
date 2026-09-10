theorem uvil_obl_28140725a8ac : ∀ (k : Int) (x : Int), ((k ≥ 1) ∧ (x ≥ (-k)) ∧ (x ≤ k)) → ((if (x < 0) then 0 else (if (x > k) then k else x)) ≤ k) := by omega
