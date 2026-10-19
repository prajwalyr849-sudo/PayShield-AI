import { createContext, useContext, useEffect, useState } from 'react'
import { getAuthMe, initiateOAuthLogin, loginDemoUser, loginWithEmail, registerWithEmail, logoutUser, unlinkProviderIdentity } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refreshUser = async () => {
    try {
      const profile = await getAuthMe()
      setUser(profile)
    } catch (err) {
      setError(err.message || 'Failed to restore session')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshUser()
  }, [])

  const loginDemo = async () => {
    setError('')
    try {
      const profile = await loginDemoUser()
      setUser(profile)
      return profile
    } catch (err) {
      setError(err.message || 'Failed to sign in as demo user')
      throw err
    }
  }

  const loginEmail = async (email, password) => {
    setError('')
    try {
      const profile = await loginWithEmail(email, password)
      setUser(profile)
      return profile
    } catch (err) {
      setError(err.message || 'Invalid email or password.')
      throw err
    }
  }

  const registerEmail = async (name, email, password, confirmPassword) => {
    setError('')
    try {
      const profile = await registerWithEmail(name, email, password, confirmPassword)
      setUser(profile)
      return profile
    } catch (err) {
      setError(err.message || 'Unable to create account.')
      throw err
    }
  }

  const loginWithOAuth = async (provider) => {
    setError('')
    try {
      const result = await initiateOAuthLogin(provider, false)
      if (result.authorization_url) {
        window.location.assign(result.authorization_url)
      } else {
        throw new Error('Authorization URL was not provided.')
      }
    } catch (err) {
      setError(err.message || `Failed to initiate ${provider} sign-in`)
      throw err
    }
  }

  const linkOAuth = async (provider) => {
    setError('')
    try {
      const result = await initiateOAuthLogin(provider, true)
      if (result.authorization_url) {
        window.location.assign(result.authorization_url)
      } else {
        throw new Error('Authorization URL was not provided.')
      }
    } catch (err) {
      setError(err.message || `Failed to initiate ${provider} account linking`)
      throw err
    }
  }

  const unlinkIdentity = async (provider) => {
    setError('')
    try {
      const updatedProfile = await unlinkProviderIdentity(provider)
      setUser(updatedProfile)
      return updatedProfile
    } catch (err) {
      setError(err.message || `Failed to unlink ${provider}`)
      throw err
    }
  }

  const logout = async () => {
    try {
      await logoutUser()
    } catch {
      // Proceed with local signout even if backend call fails
    } finally {
      setUser(null)
      setError('')
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        setError,
        loginDemo,
        loginEmail,
        registerEmail,
        loginWithOAuth,
        linkOAuth,
        unlinkIdentity,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
