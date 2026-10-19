using UnityEngine;
using VoxelWorld.Core;
using VoxelWorld.Voxel;
using VoxelWorld.World;

namespace VoxelWorld.Player
{
    /// <summary>
    /// First-person movement with kinematic box-versus-voxel collision. The player lives in the
    /// world root's local space, where one unit equals one block, so the block size setting
    /// scales the whole world (player included) uniformly.
    /// </summary>
    public sealed class PlayerController : MonoBehaviour
    {
        [Header("Body")]
        [SerializeField] private float width = 0.6f;
        [SerializeField] private float height = 1.8f;
        [SerializeField] private float eyeHeight = 1.62f;

        [Header("Movement (blocks per second)")]
        [SerializeField] private float walkSpeed = 4.3f;
        [SerializeField] private float sprintSpeed = 6.4f;
        [SerializeField] private float groundAcceleration = 60f;
        [SerializeField] private float airAcceleration = 14f;
        [SerializeField] private float groundFriction = 45f;
        [SerializeField] private float jumpVelocity = 8.6f;
        [SerializeField] private float gravity = 28f;
        [SerializeField] private float terminalVelocity = 60f;
        [SerializeField] private float coyoteTime = 0.1f;
        [SerializeField] private float jumpBuffer = 0.12f;

        [Header("Water")]
        [SerializeField] private float swimSpeed = 2.6f;
        [SerializeField] private float waterGravity = 7f;
        [SerializeField] private float swimUpSpeed = 3.6f;

        [Header("Look")]
        [Tooltip("Degrees of rotation per pixel of mouse movement at sensitivity 1.")]
        [SerializeField] private float degreesPerPixel = 0.11f;
        [SerializeField] private float sprintFovBoost = 8f;

        private WorldManager _world;
        private Transform _head;
        private Camera _camera;
        private Vector3 _velocity;
        private float _pitch;
        private float _yaw;
        private float _lastGroundedTime = -10f;
        private float _lastJumpPressTime = -10f;
        private float _fovCurrent;
        private float _bobPhase;

        public bool IsGrounded { get; private set; }
        public bool IsInWater { get; private set; }
        public bool IsSprinting { get; private set; }
        public Vector3 Velocity => _velocity;
        public float Width => width;
        public float Height => height;
        public Transform Head => _head;
        public Camera Camera => _camera;

        /// <summary>Feet position in block coordinates.</summary>
        public Vector3 Position => transform.localPosition;

        /// <summary>Eye position in block coordinates.</summary>
        public Vector3 EyePosition => transform.localPosition + Vector3.up * eyeHeight;

        /// <summary>Raised when the player lands; argument is the downward speed at impact (for fall damage later).</summary>
        public event System.Action<float> Landed;

        public void Initialize(WorldManager world, Camera camera)
        {
            _world = world;
            _camera = camera;
            _head = new GameObject("Head").transform;
            _head.SetParent(transform, false);
            _head.localPosition = new Vector3(0f, eyeHeight, 0f);
            camera.transform.SetParent(_head, false);
            camera.transform.localPosition = Vector3.zero;
            camera.transform.localRotation = Quaternion.identity;
            _fovCurrent = GameSettings.FieldOfView;
            camera.fieldOfView = _fovCurrent;
        }

        public void Teleport(Vector3 feetPosition, float yaw = float.NaN)
        {
            transform.localPosition = feetPosition;
            _velocity = Vector3.zero;
            if (!float.IsNaN(yaw)) _yaw = yaw;
            ApplyRotation();
        }

        /// <summary>World-local box occupied by the player.</summary>
        public VoxelBox Bounds
        {
            get
            {
                var p = transform.localPosition;
                return VoxelBox.FromFeet(p.x, p.y, p.z, width, height);
            }
        }

        private void Update()
        {
            if (_world == null) return;
            float dt = Mathf.Min(Time.deltaTime, 0.05f);
            bool inputActive = !GameState.InputBlocked;

            if (inputActive) Look();
            Move(dt, inputActive);
            UpdateCameraEffects(dt);
            _world.SetFocus(transform.localPosition);
        }

        private void Look()
        {
            Vector2 delta = GameInput.LookDelta * (degreesPerPixel * GameSettings.MouseSensitivity);
            _yaw = Mathf.Repeat(_yaw + delta.x, 360f);
            _pitch = Mathf.Clamp(_pitch + (GameSettings.InvertY ? delta.y : -delta.y), -89f, 89f);
            ApplyRotation();
        }

        private void ApplyRotation()
        {
            transform.localRotation = Quaternion.Euler(0f, _yaw, 0f);
            if (_head != null) _head.localRotation = Quaternion.Euler(_pitch, 0f, 0f);
        }

        private void Move(float dt, bool inputActive)
        {
            var registry = _world.Registry;
            var pos = transform.localPosition;
            var box = VoxelBox.FromFeet(pos.x, pos.y, pos.z, width, height);
            IsInWater = VoxelPhysics.TouchesLiquid(_world, registry, box);

            Vector2 input = inputActive ? GameInput.Move : Vector2.zero;
            IsSprinting = inputActive && GameInput.SprintHeld && input.y > 0.1f && !IsInWater;
            float speed = IsInWater ? swimSpeed : (IsSprinting ? sprintSpeed : walkSpeed);

            Vector3 forward = transform.localRotation * Vector3.forward;
            Vector3 right = transform.localRotation * Vector3.right;
            Vector3 wish = (forward * input.y + right * input.x) * speed;

            // Horizontal acceleration toward the wished velocity; friction when there is no input.
            var horizontal = new Vector3(_velocity.x, 0f, _velocity.z);
            float accel = IsGrounded ? groundAcceleration : airAcceleration;
            if (input.sqrMagnitude < 0.01f && IsGrounded) accel = groundFriction;
            horizontal = Vector3.MoveTowards(horizontal, wish, accel * dt);
            _velocity.x = horizontal.x;
            _velocity.z = horizontal.z;

            if (inputActive && GameInput.JumpPressed) _lastJumpPressTime = Time.time;

            if (IsInWater)
            {
                _velocity.y -= waterGravity * dt;
                _velocity.y *= 1f - Mathf.Min(1f, 2.5f * dt);
                if (inputActive && GameInput.JumpHeld) _velocity.y = Mathf.MoveTowards(_velocity.y, swimUpSpeed, 30f * dt);
                _velocity.y = Mathf.Max(_velocity.y, -4f);
            }
            else
            {
                _velocity.y = Mathf.Max(_velocity.y - gravity * dt, -terminalVelocity);
                bool canJump = Time.time - _lastGroundedTime <= coyoteTime;
                bool wantsJump = Time.time - _lastJumpPressTime <= jumpBuffer;
                if (canJump && wantsJump)
                {
                    _velocity.y = jumpVelocity;
                    _lastGroundedTime = -10f;
                    _lastJumpPressTime = -10f;
                }
            }

            float x = pos.x, y = pos.y, z = pos.z;
            float fallSpeed = -_velocity.y;
            var flags = VoxelPhysics.Move(_world, registry, ref x, ref y, ref z, width, height,
                _velocity.x * dt, _velocity.y * dt, _velocity.z * dt);

            bool wasGrounded = IsGrounded;
            IsGrounded = (flags & VoxelCollision.Ground) != 0;
            if (IsGrounded)
            {
                _lastGroundedTime = Time.time;
                if (!wasGrounded && fallSpeed > 0f) Landed?.Invoke(fallSpeed);
                if (_velocity.y < 0f) _velocity.y = 0f;
            }
            if ((flags & VoxelCollision.Ceiling) != 0 && _velocity.y > 0f) _velocity.y = 0f;
            if ((flags & VoxelCollision.WallX) != 0) _velocity.x = 0f;
            if ((flags & VoxelCollision.WallZ) != 0) _velocity.z = 0f;

            // Climb out of water onto a ledge when swimming against it.
            if (IsInWater && inputActive && (flags & (VoxelCollision.WallX | VoxelCollision.WallZ)) != 0 && GameInput.JumpHeld)
                _velocity.y = Mathf.Max(_velocity.y, 5.5f);

            // Ground probe: while standing still the downward move is tiny, so check explicitly.
            if (!IsGrounded && _velocity.y <= 0f)
            {
                var probe = VoxelBox.FromFeet(x, y - 0.02f, z, width - 0.01f, 0.02f);
                if (VoxelPhysics.Overlaps(_world, registry, probe))
                {
                    IsGrounded = true;
                    _lastGroundedTime = Time.time;
                }
            }

            transform.localPosition = new Vector3(x, y, z);
        }

        private void UpdateCameraEffects(float dt)
        {
            if (_camera == null) return;
            float targetFov = GameSettings.FieldOfView + (IsSprinting ? sprintFovBoost : 0f);
            _fovCurrent = Mathf.Lerp(_fovCurrent, targetFov, 1f - Mathf.Exp(-10f * dt));
            _camera.fieldOfView = _fovCurrent;

            // Subtle head bob while walking on the ground.
            float horizontalSpeed = new Vector2(_velocity.x, _velocity.z).magnitude;
            if (IsGrounded && horizontalSpeed > 0.5f) _bobPhase += dt * horizontalSpeed * 1.9f;
            float amount = IsGrounded ? Mathf.Clamp01(horizontalSpeed / sprintSpeed) * 0.045f : 0f;
            _head.localPosition = new Vector3(Mathf.Cos(_bobPhase) * amount * 0.5f,
                eyeHeight + Mathf.Abs(Mathf.Sin(_bobPhase)) * amount, 0f);
        }
    }
}
