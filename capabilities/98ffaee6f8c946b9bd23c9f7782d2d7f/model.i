# VIBORA model: updated-Lagrangian thermoelastic compressible neo-Hookean solid
# Units: length mm, time ms, stress MPa (N/mm^2), mass g, energy mJ, temperature K
# Requires the new ViboraPhysicsApp material ComputeLagrangianThermoCompressibleNeoHookeanStress

[GlobalParams]
  displacements = 'disp_x disp_y'
[]

[Mesh]
  type = GeneratedMesh
  dim = 2
  nx = 20
  ny = 20
  xmin = 0
  xmax = 1
  ymin = 0
  ymax = 1
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
  [temperature]
    family = LAGRANGE
    order = FIRST
  []
[]

[ICs]
  [initial_temperature]
    type = ConstantIC
    variable = temperature
    value = 300 # K
  []
[]

[Functions]
  [left_push_function]
    type = ParsedFunction
    expression = '0.1*t' # mm (t in ms)
  []
[]

[BCs]
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
    type = FunctionDirichletBC
    variable = disp_x
    boundary = left
    function = left_push_function
  []
  # temperature: no BCs -> adiabatic (zero-flux natural condition)
[]

[Physics/SolidMechanics/QuasiStatic]
  [all]
    new_system = true
    formulation = UPDATED
    strain = FINITE
    add_variables = false
    generate_output = 'cauchy_stress_xx cauchy_stress_yy cauchy_stress_zz cauchy_stress_xy'
  []
[]

[Materials]
  [material_constants]
    type = GenericConstantMaterial
    prop_names = 'bulk shear'
    prop_values = '1000 1000' # MPa (1 GPa)
    constant_on = ELEMENT
  []
  [thermal_constants]
    type = GenericConstantMaterial
    prop_names = 'density specific_heat alpha'
    prop_values = '1e-3 1000 1e-5' # g/mm^3, mJ/(g K), 1/K
    constant_on = ELEMENT
  []
  [thermal_conductivity_current]
    type = GenericConstantMaterial
    prop_names = 'thermal_conductivity'
    prop_values = '1e-3' # mJ/(ms mm K) = 1 W/(m K)
    constant_on = ELEMENT
    use_displaced_mesh = true
  []
  [stress_constitutive_model]
    type = ComputeLagrangianThermoCompressibleNeoHookeanStress
    bulk_modulus = bulk
    shear_modulus = shear
    deviatoric_form = isochoric
    temperature = temperature
    thermal_expansion_coefficient = alpha
    stress_free_temperature = 300 # K
    thermal_stretch_form = linear
    jacobian_name = J
    jacobian_rate_name = J_dot
  []
  [thermomechanical_coupling]
    type = ParsedMaterial
    property_name = thermoelastic_rate
    material_property_names = 'bulk alpha J_dot'
    # reference-volume form of -3*K*alpha*T*Jdot/J (current volume); T supplied by MatReaction
    expression = '-3*bulk*alpha*J_dot'
    enable_jit = false
  []
[]

[Kernels]
  [accumulation]
    type = HeatConductionTimeDerivative
    variable = temperature
    density_name = density
    specific_heat = specific_heat
    use_displaced_mesh = false
  []
  [heat_conduction]
    type = HeatConduction
    variable = temperature
    thermal_conductivity = thermal_conductivity
    use_displaced_mesh = true
  []
  [volumetric_compression_heating]
    type = MatReaction
    variable = temperature
    reaction_rate = thermoelastic_rate
    use_displaced_mesh = false
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
  automatic_scaling = true
  nl_rel_tol = 1e-8
  nl_abs_tol = 1e-10
  nl_max_its = 30
[]

[Outputs]
  [results]
    type = Exodus
    show = 'cauchy_stress_xx cauchy_stress_yy cauchy_stress_zz cauchy_stress_xy'
    time_step_interval = 3
  []
[]
