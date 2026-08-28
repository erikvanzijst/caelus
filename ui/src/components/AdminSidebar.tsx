import {
  GroupOutlined,
  Inventory2Outlined,
  LocalOfferOutlined,
  RocketLaunchOutlined,
} from '@mui/icons-material'
import { SectionSidebar, type SectionNavItem } from './SectionSidebar'

const navItems: SectionNavItem[] = [
  { label: 'Products', path: '/admin/products', icon: <Inventory2Outlined /> },
  { label: 'Deployments', path: '/admin/deployments', icon: <RocketLaunchOutlined /> },
  { label: 'Users', path: '/admin/users', icon: <GroupOutlined /> },
  { label: 'Plans', path: '/admin/plans', icon: <LocalOfferOutlined /> },
]

export function AdminSidebar() {
  return <SectionSidebar items={navItems} />
}
