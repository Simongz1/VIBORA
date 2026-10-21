# Quasi-static (transient, no inertia) updated-Lagrangian finite-deformation mechanics
# Compressible neo-Hookean: W = K/2 (J-1)^2 + G/2 (tr b - 3), P = dW/dF

[GlobalParams]
  displacements = 'disp_x disp_y'
[]

[Mesh]
  type = GeneratedMesh
  dim = 2
  nx = 20
  ny = 20
  # default domain [0,1] x [0,1]; no physical length unit assigned
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
        add_variables = false
        generate_output = 'cauchy_stress_xx cauchy_stress_yy cauchy_stress_xy'
      []
    []
  []
[]

[Functions]
  [left_push]
    type = ParsedFunction
    expression = '0.1*t'
  []
[]

[BCs]
  # u . n = 0 on top/bottom (normal is +/- y)
  [no_vertical_displacement]
    type = DirichletBC
    variable = disp_y
    boundary = 'top bottom'
    value = 0
  []
  # u . n = 0 on right (normal is +x)
  [no_horizontal_displacement]
    type = DirichletBC
    variable = disp_x
    boundary = 'right'
    value = 0
  []
  # constant-velocity push 0.1*t on the left edge (description overrides stored value = 0)
  [left_push]
    type = FunctionDirichletBC
    variable = disp_x
    boundary = 'left'
    function = left_push
  []
[]

[Materials]
  [material_constants]
    type = GenericConstantMaterial
    prop_names = 'bulk shear'
    prop_values = '1e9 1e9' # 1 GPa each, assuming SI (Pa)
    constant_on = ELEMENT
  []
  [stress]
    type = ComputeLagrangianCompressibleNeoHookeanStress
    bulk_modulus = bulk
    shear_modulus = shear
    deviatoric_form = literal # G/2 (tr b - 3) as specified; 'isochoric' available
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
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
  dt = 0.1
  num_steps = 10
[]

[Outputs]
  exodus = true
[]
