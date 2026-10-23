# nm, ns, GPa, K. Derived mass unit: 1e-18 kg.
[Mesh]
  type = GeneratedMesh
  dim = 2
  nx = 250
  ny = 250
  xmin = 0
  xmax = 100
  ymin = 0
  ymax = 100
  displacements = 'disp_x disp_y'
[]
[Variables]
  [temperature]
  []
  [Y1]
    initial_condition = 1
  []
  [Y2]
    initial_condition = 0
  []
  [Y3]
    initial_condition = 0
  []
  [disp_x]
    initial_condition = 0
  []
  [disp_y]
    initial_condition = 0
  []
[]
[Functions]
  [hotspot]
    type = ParsedFunction
    expression = 'if((x-50)^2+(y-50)^2<=25,1920,300)'
  []
[]
[ICs]
  [hotspot]
    type = FunctionIC
    variable = temperature
    function = hotspot
  []
[]
[AuxVariables]
  [vel_x]
    initial_condition = 0
  []
  [vel_y]
    initial_condition = 0
  []
  [accel_x]
    initial_condition = 0
  []
  [accel_y]
    initial_condition = 0
  []
[]
[AuxKernels]
  [ax]
    type = NewmarkAccelAux
    variable = accel_x
    displacement = disp_x
    velocity = vel_x
    beta = 0.25
    execute_on = TIMESTEP_END
  []
  [ay]
    type = NewmarkAccelAux
    variable = accel_y
    displacement = disp_y
    velocity = vel_y
    beta = 0.25
    execute_on = TIMESTEP_END
  []
  [vx]
    type = NewmarkVelAux
    variable = vel_x
    acceleration = accel_x
    gamma = 0.5
    execute_on = TIMESTEP_END
  []
  [vy]
    type = NewmarkVelAux
    variable = vel_y
    acceleration = accel_y
    gamma = 0.5
    execute_on = TIMESTEP_END
  []
[]
[Materials]
  [constants]
    type = GenericConstantMaterial
    constant_on = ELEMENT
    prop_names = 'rho0 specific_heat thermal_conductivity shear bulk alpha'
    prop_values = '1.82e-6 2355.592 0.361 10 16 1e-4'
  []
  [kinematics]
    type = ComputeLagrangianStrain
    displacements = 'disp_x disp_y'
    large_kinematics = true
    stabilize_strain = false
  []
  [constitutive]
    type = ViboraHotspotJWLJ2
    temperature = temperature
    reactant = Y1
    reference_density = rho0
    specific_heat = specific_heat
    shear_modulus = shear
    output_properties = 'J J_dot current_density equivalent_plastic_strain pressure'
    outputs = exodus
  []
  [r1]
    type = DerivativeParsedMaterial
    property_name = r1
    coupled_variables = temperature
    expression = '1e-9*exp(31.1-24.4*4184/(8.31446261815324*temperature))'
    derivative_order = 1
    enable_jit = false
  []
  [minus_r1]
    type = DerivativeParsedMaterial
    property_name = minus_r1
    coupled_variables = temperature
    expression = '-1e-9*exp(31.1-24.4*4184/(8.31446261815324*temperature))'
    derivative_order = 1
    enable_jit = false
  []
  [r2]
    type = DerivativeParsedMaterial
    property_name = r2
    coupled_variables = temperature
    expression = '1e-9*exp(30.1-23.5*4184/(8.31446261815324*temperature))'
    derivative_order = 1
    enable_jit = false
  []
  [minus_r2]
    type = DerivativeParsedMaterial
    property_name = minus_r2
    coupled_variables = temperature
    expression = '-1e-9*exp(30.1-23.5*4184/(8.31446261815324*temperature))'
    derivative_order = 1
    enable_jit = false
  []
  # MatReaction contributes -coefficient * temperature.
  # Thus this coefficient gives the literal positive heat-release RHS.
  [reaction_heat_coefficient]
    type = DerivativeParsedMaterial
    property_name = reaction_heat_coefficient
    coupled_variables = 'temperature Y1 Y2'
    expression = '1.82e-6*4184/0.222*((-1.7+0.0314*(temperature-1736.3))*1e-9*exp(31.1-24.4*4184/(8.31446261815324*temperature))*Y1+(416-0.03836*(temperature-1736.3))*1e-9*exp(30.1-23.5*4184/(8.31446261815324*temperature))*Y2)/temperature'
    derivative_order = 1
    enable_jit = false
  []
  [compression_coefficient]
    type = DerivativeParsedMaterial
    property_name = compression_coefficient
    material_property_names = 'J J_dot'
    expression = '-3*1e-4*16*J_dot/J'
    derivative_order = 1
    enable_jit = false
  []
[]
[Kernels]
  [thermal_accumulation]
    type = HeatConductionTimeDerivative
    variable = temperature
    density_name = rho0
    specific_heat = specific_heat
    use_displaced_mesh = true
  []
  [conduction]
    type = HeatConduction
    variable = temperature
    use_displaced_mesh = true
  []
  [reaction_heat]
    type = MatReaction
    variable = temperature
    reaction_rate = reaction_heat_coefficient
    args = 'Y1 Y2'
    use_displaced_mesh = true
  []
  [compression_heat]
    type = MatReaction
    variable = temperature
    reaction_rate = compression_coefficient
    use_displaced_mesh = true
  []
  [Y1_time]
    type = TimeDerivative
    variable = Y1
    use_displaced_mesh = true
  []
  [Y2_time]
    type = TimeDerivative
    variable = Y2
    use_displaced_mesh = true
  []
  [Y3_time]
    type = TimeDerivative
    variable = Y3
    use_displaced_mesh = true
  []
  [Y1_loss]
    type = MatReaction
    variable = Y1
    reaction_rate = minus_r1
    args = temperature
    use_displaced_mesh = true
  []
  [Y2_gain]
    type = MatReaction
    variable = Y2
    v = Y1
    reaction_rate = r1
    args = temperature
    use_displaced_mesh = true
  []
  [Y2_loss]
    type = MatReaction
    variable = Y2
    reaction_rate = minus_r2
    args = temperature
    use_displaced_mesh = true
  []
  [Y3_gain]
    type = MatReaction
    variable = Y3
    v = Y2
    reaction_rate = r2
    args = temperature
    use_displaced_mesh = true
  []
  [stress_x]
    type = UpdatedLagrangianStressDivergence
    variable = disp_x
    component = 0
    displacements = 'disp_x disp_y'
    use_displaced_mesh = true
  []
  [stress_y]
    type = UpdatedLagrangianStressDivergence
    variable = disp_y
    component = 1
    displacements = 'disp_x disp_y'
    use_displaced_mesh = true
  []
  [inertia_x]
    type = InertialForce
    variable = disp_x
    density = current_density
    velocity = vel_x
    acceleration = accel_x
    beta = 0.25
    gamma = 0.5
    use_displaced_mesh = true
  []
  [inertia_y]
    type = InertialForce
    variable = disp_y
    density = current_density
    velocity = vel_y
    acceleration = accel_y
    beta = 0.25
    gamma = 0.5
    use_displaced_mesh = true
  []
[]
[BCs]
  [reflect_x]
    type = DirichletBC
    variable = disp_x
    boundary = 'left right'
    value = 0
  []
  [reflect_y]
    type = DirichletBC
    variable = disp_y
    boundary = 'bottom top'
    value = 0
  []
[]
[VectorPostprocessors]
  [centerline]
    type = LineValueSampler
    variable = temperature
    start_point = '0 50 0'
    end_point = '100 50 0'
    num_points = 251
    sort_by = x
    execute_on = TIMESTEP_END
    outputs = profiles
  []
[]
[Executioner]
  type = Transient
  solve_type = PJFNK
  scheme = implicit-euler
  dt = 0.001
  dtmin = 0.001
  dtmax = 0.001
  num_steps = 200
  end_time = 0.2
  abort_on_solve_fail = true
  automatic_scaling = true
  nl_rel_tol = 1e-8
  nl_abs_tol = 1e-10
  nl_max_its = 40
  petsc_options_iname = '-pc_type -sub_pc_type'
  petsc_options_value = 'asm ilu'
[]
[Outputs]
  [exodus]
    type = Exodus
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [profiles]
    type = CSV
    execute_on = TIMESTEP_END
    sync_only = true
    sync_times = '0.025 0.050 0.075'
    time_data = true
    precision = 16
  []
[]
