[GlobalParams]
  displacements = 'disp_x disp_y'
[]

[Mesh]
  type = GeneratedMesh
  dim = 2
  nx = 20
  ny = 20
[]

[Variables]
  [disp_x]
    family = LAGRANGE
    order = FIRST
  []
  [disp_y]
    family = LAGRANGE
    order = FIRST
  []
[]

[Physics]
  [SolidMechanics]
    [QuasiStatic]
      [all]
        new_system = true
        formulation = UPDATED
        strain = FINITE
        generate_output = 'cauchy_stress_xx cauchy_stress_yy cauchy_stress_xy vonmises_cauchy_stress'
      []
    []
  []
[]

[BCs]
  # u.n = 0 on axis-aligned straight edges == normal component fixed to zero
  [no_vertical_displacement]
    type = DirichletBC
    variable = disp_y
    boundary = 'top bottom'
    value = 0
  []
  [no_horizontal_displacement]
    type = DirichletBC
    variable = disp_x
    boundary = right
    value = 0
  []
  [left_push]
    type = DirichletBC
    variable = disp_x
    boundary = left
    value = 0
  []
[]

[Materials]
  [material_constants]
    type = GenericConstantMaterial
    prop_names = 'bulk shear'
    prop_values = '1e9 1e9' # 1 GPa each (SI pressure units assumed)
    constant_on = ELEMENT
  []
  [stress]
    # W = K/2 (J-1)^2 + G/2 (tr b - 3)  ->  P = G F + K J (J-1) F^{-T}
    type = ComputeLagrangianCompressibleNeoHookeanStress
    bulk_modulus = bulk
    shear_modulus = shear
    deviatoric_form = literal
  []
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Executioner]
  type = Transient
  solve_type = PJFNK
  scheme = implicit-euler
  dt = 0.1
  num_steps = 10
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
  nl_rel_tol = 1e-8
  # residual round-off at GPa moduli is ~1e-8..1e-7; element force scale ~1e7
  nl_abs_tol = 1e-3
[]

[Outputs]
  exodus = true
[]
